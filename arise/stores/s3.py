from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime

from arise.stores.base import SkillStore, SkillStoreWriter
from arise.types import Skill, SkillOrigin, SkillStatus, ToolSpec


def _skill_to_dict(skill: Skill) -> dict:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "implementation": skill.implementation,
        "test_suite": skill.test_suite,
        "version": skill.version,
        "status": skill.status.value,
        "origin": skill.origin.value,
        "parent_id": skill.parent_id,
        "created_at": skill.created_at.isoformat(),
        "invocation_count": skill.invocation_count,
        "success_count": skill.success_count,
        "avg_latency_ms": skill.avg_latency_ms,
        "error_log": skill.error_log,
    }


def _dict_to_skill(d: dict) -> Skill:
    return Skill(
        id=d["id"],
        name=d["name"],
        description=d.get("description", ""),
        implementation=d["implementation"],
        test_suite=d.get("test_suite", ""),
        version=d.get("version", 1),
        status=SkillStatus(d.get("status", "testing")),
        origin=SkillOrigin(d.get("origin", "synthesized")),
        parent_id=d.get("parent_id"),
        created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else datetime.now(),
        invocation_count=d.get("invocation_count", 0),
        success_count=d.get("success_count", 0),
        avg_latency_ms=d.get("avg_latency_ms", 0.0),
        error_log=d.get("error_log", []),
    )


class S3SkillStore(SkillStore):
    """Read-only S3-backed skill store with TTL cache.

    S3 layout:
        s3://{bucket}/{prefix}/manifest.json    {"version": N, "active_skill_ids": [...]}
        s3://{bucket}/{prefix}/skills/{id}.json  Serialized Skill
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "arise",
        region: str = "us-east-1",
        cache_ttl: int = 30,
        s3_client: object | None = None,
    ):
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")
        self._cache_ttl = cache_ttl
        self._lock = threading.Lock()

        # Cache state
        self._cached_version: int = 0
        self._cached_skills: list[Skill] = []
        self._last_refresh: float = 0.0

        if s3_client is not None:
            self._s3 = s3_client
        else:
            import boto3
            self._s3 = boto3.client("s3", region_name=region)

    def get_version(self) -> int:
        self._maybe_refresh()
        return self._cached_version

    def get_active_skills(self) -> list[Skill]:
        self._maybe_refresh()
        return list(self._cached_skills)

    def get_tool_specs(self) -> list[ToolSpec]:
        skills = self.get_active_skills()
        specs = []
        for skill in skills:
            try:
                specs.append(skill.to_tool_spec())
            except Exception:
                continue
        return specs

    def _maybe_refresh(self) -> None:
        now = time.time()
        if now - self._last_refresh < self._cache_ttl:
            return

        with self._lock:
            # Double-check after acquiring lock
            if now - self._last_refresh < self._cache_ttl:
                return
            try:
                manifest = self._read_manifest()
                if manifest["version"] != self._cached_version:
                    skills = []
                    for skill_id in manifest["active_skill_ids"]:
                        skill = self._read_skill(skill_id)
                        if skill is not None:
                            skills.append(skill)
                    self._cached_skills = skills
                    self._cached_version = manifest["version"]
                self._last_refresh = time.time()
            except Exception as e:
                # Graceful degradation: use stale cache
                print(f"[ARISE] S3 refresh failed, using stale cache: {e}", file=sys.stderr)
                self._last_refresh = time.time()

    def _read_manifest(self) -> dict:
        key = f"{self._prefix}/manifest.json"
        resp = self._s3.get_object(Bucket=self._bucket, Key=key)
        return json.loads(resp["Body"].read())

    def _read_skill(self, skill_id: str) -> Skill | None:
        key = f"{self._prefix}/skills/{skill_id}.json"
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
            data = json.loads(resp["Body"].read())
            return _dict_to_skill(data)
        except Exception:
            return None

    def _manifest_key(self) -> str:
        return f"{self._prefix}/manifest.json"

    def _skill_key(self, skill_id: str) -> str:
        return f"{self._prefix}/skills/{skill_id}.json"


class S3SkillStoreWriter(S3SkillStore, SkillStoreWriter):
    """Read-write S3-backed skill store for the worker process."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "arise",
        region: str = "us-east-1",
        cache_ttl: int = 5,
        s3_client: object | None = None,
    ):
        super().__init__(bucket, prefix, region, cache_ttl, s3_client)
        # Ensure manifest exists
        try:
            self._read_manifest()
        except Exception:
            self._write_manifest({"version": 0, "active_skill_ids": []})

    def add(self, skill: Skill) -> Skill:
        self._write_skill(skill)
        return skill

    def promote(self, skill_id: str) -> Skill:
        skill = self.get_skill(skill_id)
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found")
        skill.status = SkillStatus.ACTIVE
        self._write_skill(skill)

        manifest = self._read_manifest()
        if skill_id not in manifest["active_skill_ids"]:
            manifest["active_skill_ids"].append(skill_id)
        manifest["version"] += 1
        self._write_manifest(manifest)

        # Invalidate cache
        self._cached_version = manifest["version"]
        self._cached_skills = [s for s in self._cached_skills if s.id != skill_id] + [skill]
        return skill

    def deprecate(self, skill_id: str, reason: str = "") -> None:
        skill = self.get_skill(skill_id)
        if skill is not None:
            skill.status = SkillStatus.DEPRECATED
            self._write_skill(skill)

        manifest = self._read_manifest()
        if skill_id in manifest["active_skill_ids"]:
            manifest["active_skill_ids"].remove(skill_id)
            manifest["version"] += 1
            self._write_manifest(manifest)
            self._cached_version = manifest["version"]
            self._cached_skills = [s for s in self._cached_skills if s.id != skill_id]

    def checkpoint(self, description: str = "") -> int:
        manifest = self._read_manifest()
        return manifest["version"]

    def get_skill(self, skill_id: str) -> Skill | None:
        return self._read_skill(skill_id)

    def _write_skill(self, skill: Skill) -> None:
        key = self._skill_key(skill.id)
        body = json.dumps(_skill_to_dict(skill))
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType="application/json")

    def _write_manifest(self, manifest: dict) -> None:
        key = self._manifest_key()
        body = json.dumps(manifest)
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType="application/json")
