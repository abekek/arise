"""Tests for registry improvements: export/import, tag search, pull validation."""

import json
import os
import sys
import tempfile

from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise.registry.client import (
    SkillRegistry,
    export_skills,
    import_skills,
)
from arise.skills.library import SkillLibrary
from arise.types import Skill, SkillOrigin, SkillStatus, SkillValidationError, SandboxResult, TestResult


# --- Helpers ---

def _make_s3_mock(objects: dict | None = None):
    storage = objects or {}
    mock = MagicMock()

    def get_object(Bucket, Key):
        if Key not in storage:
            raise Exception(f"NoSuchKey: {Key}")
        body = MagicMock()
        body.read.return_value = storage[Key]
        return {"Body": body}

    def put_object(Bucket, Key, Body, **kwargs):
        storage[Key] = Body.encode() if isinstance(Body, str) else Body

    mock.get_object = MagicMock(side_effect=get_object)
    mock.put_object = MagicMock(side_effect=put_object)
    mock._storage = storage
    return mock


def _make_skill(name="add_numbers", description="Add two numbers together"):
    return Skill(
        name=name,
        description=description,
        implementation=f"def {name}(a, b):\n    return a + b",
        test_suite=f"def test_{name}():\n    assert {name}(1, 2) == 3",
        origin=SkillOrigin.SYNTHESIZED,
    )


def _make_library(tmpdir):
    return SkillLibrary(os.path.join(tmpdir, "skills"))


# --- export_skills ---

def test_export_skills_writes_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        lib = _make_library(tmpdir)
        s1 = _make_skill("add_numbers", "Add two numbers")
        lib.add(s1)
        lib.promote(s1.id)
        s2 = _make_skill("multiply", "Multiply two numbers")
        lib.add(s2)
        lib.promote(s2.id)

        out_path = os.path.join(tmpdir, "exported.json")
        count = export_skills(lib, out_path)

        assert count == 2
        data = json.loads(open(out_path).read())
        assert len(data) == 2
        names = {d["name"] for d in data}
        assert names == {"add_numbers", "multiply"}
        for record in data:
            assert "implementation" in record
            assert "name" in record
            assert "description" in record
            assert "version" in record
            assert "tags" in record
            assert "test_suite" in record


def test_export_skills_empty_library():
    with tempfile.TemporaryDirectory() as tmpdir:
        lib = _make_library(tmpdir)
        out_path = os.path.join(tmpdir, "exported.json")
        count = export_skills(lib, out_path)
        assert count == 0
        data = json.loads(open(out_path).read())
        assert data == []


# --- import_skills ---

def test_import_skills_adds_to_library():
    with tempfile.TemporaryDirectory() as tmpdir:
        lib = _make_library(tmpdir)
        records = [
            {
                "name": "parse_csv",
                "description": "Parse CSV data",
                "implementation": "def parse_csv(data):\n    return data.split(',')",
                "test_suite": "def test_parse_csv():\n    assert parse_csv('a,b') == ['a', 'b']",
                "tags": ["csv"],
                "version": 1,
            },
        ]
        in_path = os.path.join(tmpdir, "import.json")
        with open(in_path, "w") as f:
            json.dump(records, f)

        imported = import_skills(in_path, lib)
        assert len(imported) == 1
        assert imported[0].name == "parse_csv"

        active = lib.get_active_skills()
        assert len(active) == 1
        assert active[0].name == "parse_csv"


def test_import_skills_with_sandbox_validation():
    with tempfile.TemporaryDirectory() as tmpdir:
        lib = _make_library(tmpdir)

        records = [
            {
                "name": "good_skill",
                "description": "Works fine",
                "implementation": "def good_skill(x):\n    return x",
                "test_suite": "",
                "tags": [],
                "version": 1,
            },
            {
                "name": "bad_skill",
                "description": "Fails tests",
                "implementation": "def bad_skill(x):\n    raise Exception('oops')",
                "test_suite": "",
                "tags": [],
                "version": 1,
            },
        ]
        in_path = os.path.join(tmpdir, "import.json")
        with open(in_path, "w") as f:
            json.dump(records, f)

        sandbox = MagicMock()
        call_count = [0]

        def mock_test_skill(skill):
            call_count[0] += 1
            if skill.name == "bad_skill":
                return SandboxResult(success=False, total_passed=0, total_failed=1)
            return SandboxResult(success=True, total_passed=1, total_failed=0)

        sandbox.test_skill = mock_test_skill

        imported = import_skills(in_path, lib, sandbox=sandbox)
        assert len(imported) == 1
        assert imported[0].name == "good_skill"
        assert call_count[0] == 2


# --- search with tags ---

def test_search_filters_by_tags():
    s3_mock = _make_s3_mock()
    registry = SkillRegistry(bucket="test-bucket", prefix="arise-registry", s3_client=s3_mock)

    registry.publish(_make_skill("add_numbers", "Add two numbers"), tags=["math", "arithmetic"])
    registry.publish(_make_skill("parse_json", "Parse JSON data"), tags=["json", "parsing"])

    results = registry.search("numbers json", tags=["math"])
    assert len(results) == 1
    assert results[0].name == "add_numbers"


def test_search_without_tags_returns_all_matches():
    s3_mock = _make_s3_mock()
    registry = SkillRegistry(bucket="test-bucket", prefix="arise-registry", s3_client=s3_mock)

    registry.publish(_make_skill("add_numbers", "Add two numbers"), tags=["math"])
    registry.publish(_make_skill("parse_json", "Parse JSON numbers"), tags=["json"])

    results = registry.search("numbers")
    assert len(results) == 2


def test_search_sorts_by_success_rate_by_default():
    s3_mock = _make_s3_mock()
    registry = SkillRegistry(bucket="test-bucket", prefix="arise-registry", s3_client=s3_mock)

    registry.publish(_make_skill("low_rate", "math tool low"), tags=["math"])
    registry.publish(_make_skill("high_rate", "math tool high"), tags=["math"])

    # Manually set success rates in S3
    low_key = "arise-registry/skills/low_rate/v1.json"
    high_key = "arise-registry/skills/high_rate/v1.json"

    low_data = json.loads(s3_mock._storage[low_key])
    low_data["avg_success_rate"] = 0.3
    s3_mock._storage[low_key] = json.dumps(low_data).encode()

    high_data = json.loads(s3_mock._storage[high_key])
    high_data["avg_success_rate"] = 0.95
    s3_mock._storage[high_key] = json.dumps(high_data).encode()

    results = registry.search("math tool")
    assert len(results) == 2
    assert results[0].name == "high_rate"
    assert results[1].name == "low_rate"


def test_search_sort_by_relevance():
    s3_mock = _make_s3_mock()
    registry = SkillRegistry(bucket="test-bucket", prefix="arise-registry", s3_client=s3_mock)

    registry.publish(_make_skill("add_numbers", "Add two numbers arithmetic math"), tags=["math", "add"])
    registry.publish(_make_skill("sort_list", "Sort a list of math items"), tags=["list"])

    results = registry.search("add numbers arithmetic math", sort_by="relevance")
    assert results[0].name == "add_numbers"


# --- pull with validation ---

def test_pull_with_validation_passes():
    s3_mock = _make_s3_mock()
    registry = SkillRegistry(bucket="test-bucket", prefix="arise-registry", s3_client=s3_mock)
    registry.publish(_make_skill())

    sandbox = MagicMock()
    sandbox.test_skill.return_value = SandboxResult(
        success=True, total_passed=1, total_failed=0
    )

    skill = registry.pull("add_numbers", validate=True, sandbox=sandbox)
    assert skill.name == "add_numbers"
    sandbox.test_skill.assert_called_once()


def test_pull_with_validation_fails_raises_error():
    s3_mock = _make_s3_mock()
    registry = SkillRegistry(bucket="test-bucket", prefix="arise-registry", s3_client=s3_mock)
    registry.publish(_make_skill())

    sandbox = MagicMock()
    sandbox.test_skill.return_value = SandboxResult(
        success=False, total_passed=0, total_failed=1
    )

    try:
        registry.pull("add_numbers", validate=True, sandbox=sandbox)
        assert False, "Should have raised SkillValidationError"
    except SkillValidationError as e:
        assert "add_numbers" in str(e)
        assert "failed sandbox validation" in str(e)


def test_pull_without_sandbox_skips_validation():
    s3_mock = _make_s3_mock()
    registry = SkillRegistry(bucket="test-bucket", prefix="arise-registry", s3_client=s3_mock)
    registry.publish(_make_skill())

    # validate=True but no sandbox — should not raise
    skill = registry.pull("add_numbers", validate=True, sandbox=None)
    assert skill.name == "add_numbers"


def test_pull_validate_false_skips_validation():
    s3_mock = _make_s3_mock()
    registry = SkillRegistry(bucket="test-bucket", prefix="arise-registry", s3_client=s3_mock)
    registry.publish(_make_skill())

    sandbox = MagicMock()
    sandbox.test_skill.return_value = SandboxResult(
        success=False, total_passed=0, total_failed=1
    )

    # validate=False should skip sandbox even though it would fail
    skill = registry.pull("add_numbers", validate=False, sandbox=sandbox)
    assert skill.name == "add_numbers"
    sandbox.test_skill.assert_not_called()


# --- SkillValidationError ---

def test_skill_validation_error_is_exception():
    assert issubclass(SkillValidationError, Exception)
    err = SkillValidationError("test error")
    assert str(err) == "test error"


# --- round-trip export/import ---

def test_export_import_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        lib1 = _make_library(os.path.join(tmpdir, "lib1"))
        s = _make_skill("roundtrip_fn", "Roundtrip test")
        lib1.add(s)
        lib1.promote(s.id)

        json_path = os.path.join(tmpdir, "roundtrip.json")
        export_skills(lib1, json_path)

        lib2 = _make_library(os.path.join(tmpdir, "lib2"))
        imported = import_skills(json_path, lib2)

        assert len(imported) == 1
        assert imported[0].name == "roundtrip_fn"
        assert imported[0].implementation == s.implementation

        active = lib2.get_active_skills()
        assert len(active) == 1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
