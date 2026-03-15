from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from typing import Callable

from arise.types import Skill, SkillOrigin, SkillStatus, ToolSpec


class SkillLibrary:
    def __init__(self, path: str = "./arise_skills"):
        self.path = path
        os.makedirs(path, exist_ok=True)
        self._db_path = os.path.join(path, "skills.db")
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                implementation TEXT NOT NULL,
                test_suite TEXT,
                version INTEGER DEFAULT 1,
                status TEXT DEFAULT 'testing',
                origin TEXT DEFAULT 'synthesized',
                parent_id TEXT,
                created_at TEXT,
                invocation_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                avg_latency_ms REAL DEFAULT 0.0,
                error_log TEXT DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS library_versions (
                version INTEGER PRIMARY KEY AUTOINCREMENT,
                active_skill_ids TEXT NOT NULL,
                created_at TEXT,
                description TEXT
            );
        """)
        self._conn.commit()

    def add(self, skill: Skill) -> Skill:
        self._conn.execute(
            """INSERT INTO skills (id, name, description, implementation, test_suite,
               version, status, origin, parent_id, created_at, invocation_count,
               success_count, avg_latency_ms, error_log)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                skill.id, skill.name, skill.description, skill.implementation,
                skill.test_suite, skill.version, skill.status.value,
                skill.origin.value, skill.parent_id,
                skill.created_at.isoformat(),
                skill.invocation_count, skill.success_count,
                skill.avg_latency_ms, json.dumps(skill.error_log),
            ),
        )
        self._conn.commit()
        return skill

    def promote(self, skill_id: str) -> Skill:
        skill = self.get_skill(skill_id)
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found")
        skill.status = SkillStatus.ACTIVE
        self._conn.execute(
            "UPDATE skills SET status = ? WHERE id = ?",
            (SkillStatus.ACTIVE.value, skill_id),
        )
        self._conn.commit()
        self.checkpoint(f"Promoted skill '{skill.name}'")
        return skill

    def deprecate(self, skill_id: str, reason: str = "") -> None:
        self._conn.execute(
            "UPDATE skills SET status = ? WHERE id = ?",
            (SkillStatus.DEPRECATED.value, skill_id),
        )
        self._conn.commit()
        self.checkpoint(f"Deprecated skill {skill_id}: {reason}")

    def get_active_skills(self) -> list[Skill]:
        rows = self._conn.execute(
            "SELECT * FROM skills WHERE status = ?", (SkillStatus.ACTIVE.value,)
        ).fetchall()
        return [self._row_to_skill(r) for r in rows]

    def get_skill(self, skill_id: str) -> Skill | None:
        row = self._conn.execute(
            "SELECT * FROM skills WHERE id = ?", (skill_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_skill(row)

    def search(self, query: str, top_k: int = 5) -> list[Skill]:
        skills = self.get_active_skills()
        if not skills:
            return []
        query_tokens = _tokenize(query)
        scored = []
        for skill in skills:
            doc_tokens = _tokenize(f"{skill.name} {skill.description}")
            score = _tfidf_similarity(query_tokens, doc_tokens)
            scored.append((score, skill))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:top_k]]

    def get_tools(self) -> list[Callable]:
        """Return active skills as callables (backward compat)."""
        skills = self.get_active_skills()
        tools = []
        for skill in skills:
            try:
                fn = skill.to_callable()
                fn.__doc__ = skill.description
                fn._arise_skill_id = skill.id  # type: ignore[attr-defined]
                tools.append(fn)
            except Exception:
                continue
        return tools

    def get_tool_specs(self) -> list[ToolSpec]:
        """Return active skills as ToolSpec objects with full schema info."""
        skills = self.get_active_skills()
        specs = []
        for skill in skills:
            try:
                specs.append(skill.to_tool_spec())
            except Exception:
                continue
        return specs

    def record_invocation(
        self, skill_id: str, success: bool, latency_ms: float, error: str | None = None
    ):
        skill = self.get_skill(skill_id)
        if skill is None:
            return
        skill.invocation_count += 1
        if success:
            skill.success_count += 1
        # Running average for latency
        n = skill.invocation_count
        skill.avg_latency_ms = skill.avg_latency_ms * (n - 1) / n + latency_ms / n
        if error:
            skill.error_log.append(error)
            skill.error_log = skill.error_log[-50:]  # Keep last 50 errors

        self._conn.execute(
            """UPDATE skills SET invocation_count = ?, success_count = ?,
               avg_latency_ms = ?, error_log = ? WHERE id = ?""",
            (
                skill.invocation_count, skill.success_count,
                skill.avg_latency_ms, json.dumps(skill.error_log), skill_id,
            ),
        )
        self._conn.commit()

    def rollback(self, version: int) -> None:
        row = self._conn.execute(
            "SELECT active_skill_ids FROM library_versions WHERE version = ?",
            (version,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Version {version} not found")
        active_ids = json.loads(row["active_skill_ids"])
        # Deprecate all currently active skills not in the target version
        self._conn.execute(
            "UPDATE skills SET status = ? WHERE status = ?",
            (SkillStatus.DEPRECATED.value, SkillStatus.ACTIVE.value),
        )
        # Reactivate skills from the target version
        for sid in active_ids:
            self._conn.execute(
                "UPDATE skills SET status = ? WHERE id = ?",
                (SkillStatus.ACTIVE.value, sid),
            )
        self._conn.commit()
        self.checkpoint(f"Rolled back to version {version}")

    def checkpoint(self, description: str = "") -> int:
        active_ids = [s.id for s in self.get_active_skills()]
        self._conn.execute(
            "INSERT INTO library_versions (active_skill_ids, created_at, description) VALUES (?, ?, ?)",
            (json.dumps(active_ids), datetime.now().isoformat(), description),
        )
        self._conn.commit()
        return self.version

    def get_version_history(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM library_versions ORDER BY version DESC"
        ).fetchall()
        return [
            {
                "version": r["version"],
                "active_skill_ids": json.loads(r["active_skill_ids"]),
                "created_at": r["created_at"],
                "description": r["description"],
            }
            for r in rows
        ]

    def export_skill(self, skill_id: str) -> str:
        skill = self.get_skill(skill_id)
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found")
        header = f'"""\nARISE Skill: {skill.name}\n{skill.description}\nVersion: {skill.version} | Origin: {skill.origin.value}\n"""\n\n'
        return header + skill.implementation

    def import_skill(self, path: str) -> Skill:
        with open(path) as f:
            code = f.read()
        # Extract function name from def statement
        match = re.search(r"def\s+(\w+)\s*\(", code)
        if not match:
            raise ValueError(f"No function definition found in {path}")
        name = match.group(1)
        skill = Skill(
            name=name,
            implementation=code,
            origin=SkillOrigin.MANUAL,
            status=SkillStatus.ACTIVE,
        )
        return self.add(skill)

    @property
    def version(self) -> int:
        row = self._conn.execute(
            "SELECT MAX(version) as v FROM library_versions"
        ).fetchone()
        return row["v"] or 0

    def stats(self) -> dict:
        active = self.get_active_skills()
        all_rows = self._conn.execute("SELECT status FROM skills").fetchall()
        total = len(all_rows)
        deprecated = sum(1 for r in all_rows if r["status"] == "deprecated")
        testing = sum(1 for r in all_rows if r["status"] == "testing")
        avg_success = (
            sum(s.success_rate for s in active) / len(active) if active else 0.0
        )
        top = sorted(active, key=lambda s: s.success_rate, reverse=True)[:5]
        return {
            "total_skills": total,
            "active": len(active),
            "testing": testing,
            "deprecated": deprecated,
            "avg_success_rate": round(avg_success, 3),
            "top_performers": [
                {"name": s.name, "success_rate": round(s.success_rate, 3), "invocations": s.invocation_count}
                for s in top
            ],
            "library_version": self.version,
        }

    def _row_to_skill(self, row: sqlite3.Row) -> Skill:
        return Skill(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            implementation=row["implementation"],
            test_suite=row["test_suite"] or "",
            version=row["version"],
            status=SkillStatus(row["status"]),
            origin=SkillOrigin(row["origin"]),
            parent_id=row["parent_id"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            invocation_count=row["invocation_count"],
            success_count=row["success_count"],
            avg_latency_ms=row["avg_latency_ms"],
            error_log=json.loads(row["error_log"]) if row["error_log"] else [],
        )


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _tfidf_similarity(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    query_counts = Counter(query_tokens)
    doc_counts = Counter(doc_tokens)
    common = set(query_counts) & set(doc_counts)
    if not common:
        return 0.0
    dot = sum(query_counts[t] * doc_counts[t] for t in common)
    mag_q = math.sqrt(sum(v * v for v in query_counts.values()))
    mag_d = math.sqrt(sum(v * v for v in doc_counts.values()))
    return dot / (mag_q * mag_d)
