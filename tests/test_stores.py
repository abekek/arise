"""Tests for distributed stores: S3 skill store, SQS reporter, local wrappers."""

import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise.config import ARISEConfig
from arise.skills.library import SkillLibrary
from arise.stores.base import SkillStore, SkillStoreWriter, TrajectoryReporter
from arise.stores.local import LocalSkillStore, LocalTrajectoryReporter
from arise.stores.s3 import S3SkillStore, S3SkillStoreWriter, _skill_to_dict, _dict_to_skill
from arise.stores.sqs import SQSTrajectoryReporter, _serialize_trajectory, deserialize_trajectory
from arise.trajectory.store import TrajectoryStore
from arise.types import Skill, SkillOrigin, SkillStatus, Step, Trajectory


# --- Serialization round-trip ---

def test_skill_serialize_roundtrip():
    skill = Skill(
        id="abc123",
        name="greet",
        description="Say hello",
        implementation="def greet(name):\n    return f'Hello {name}'",
        test_suite="def test_greet():\n    assert greet('X') == 'Hello X'",
        version=2,
        status=SkillStatus.ACTIVE,
        origin=SkillOrigin.SYNTHESIZED,
        parent_id="parent1",
    )
    d = _skill_to_dict(skill)
    restored = _dict_to_skill(d)
    assert restored.id == "abc123"
    assert restored.name == "greet"
    assert restored.status == SkillStatus.ACTIVE
    assert restored.origin == SkillOrigin.SYNTHESIZED
    assert restored.version == 2
    assert restored.parent_id == "parent1"
    assert "Hello" in restored.implementation


def test_trajectory_serialize_roundtrip():
    traj = Trajectory(
        task="do something",
        steps=[
            Step(observation="obs", reasoning="why", action="act", result="res", latency_ms=10.0),
            Step(observation="obs2", reasoning="", action="err", error="boom", latency_ms=5.0),
        ],
        outcome="done",
        reward=0.8,
        skill_library_version=3,
        metadata={"key": "value"},
    )
    body = _serialize_trajectory(traj)
    restored = deserialize_trajectory(body)
    assert restored.task == "do something"
    assert len(restored.steps) == 2
    assert restored.steps[0].result == "res"
    assert restored.steps[1].error == "boom"
    assert restored.outcome == "done"
    assert restored.reward == 0.8
    assert restored.skill_library_version == 3
    assert restored.metadata == {"key": "value"}


# --- Local store wrappers ---

def test_local_skill_store_delegates():
    tmp = tempfile.mkdtemp()
    try:
        library = SkillLibrary(os.path.join(tmp, "skills"))
        store = LocalSkillStore(library)

        skill = Skill(
            name="add",
            description="Add two numbers",
            implementation="def add(a, b):\n    return a + b",
            origin=SkillOrigin.MANUAL,
        )
        store.add(skill)
        store.promote(skill.id)

        assert store.get_version() > 0
        active = store.get_active_skills()
        assert len(active) == 1
        assert active[0].name == "add"

        specs = store.get_tool_specs()
        assert len(specs) == 1
        assert specs[0].name == "add"

        found = store.get_skill(skill.id)
        assert found is not None
        assert found.name == "add"

        store.record_invocation(skill.id, True, 10.0)
        updated = store.get_skill(skill.id)
        assert updated.invocation_count == 1

        store.deprecate(skill.id, "test")
        assert len(store.get_active_skills()) == 0
    finally:
        shutil.rmtree(tmp)


def test_local_trajectory_reporter():
    tmp = tempfile.mkdtemp()
    try:
        traj_store = TrajectoryStore(os.path.join(tmp, "traj"))
        reporter = LocalTrajectoryReporter(traj_store)

        traj = Trajectory(task="test task", outcome="ok", reward=1.0)
        reporter.report(traj)

        recent = traj_store.get_recent(5)
        assert len(recent) == 1
        assert recent[0].task == "test task"
    finally:
        shutil.rmtree(tmp)


# --- S3 skill store (mocked) ---

def _make_s3_mock(objects: dict[str, bytes] | None = None):
    """Create a mock S3 client backed by an in-memory dict."""
    storage = objects or {}

    mock = MagicMock()

    def get_object(Bucket, Key):
        if Key not in storage:
            error = MagicMock()
            error.response = {"Error": {"Code": "NoSuchKey"}}
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


def test_s3_skill_store_read():
    skill = Skill(
        id="s1",
        name="multiply",
        description="Multiply numbers",
        implementation="def multiply(a, b):\n    return a * b",
        status=SkillStatus.ACTIVE,
    )
    manifest = {"version": 1, "active_skill_ids": ["s1"]}
    skill_data = _skill_to_dict(skill)

    s3_mock = _make_s3_mock({
        "arise/manifest.json": json.dumps(manifest).encode(),
        "arise/skills/s1.json": json.dumps(skill_data).encode(),
    })

    store = S3SkillStore(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=0)

    assert store.get_version() == 1
    skills = store.get_active_skills()
    assert len(skills) == 1
    assert skills[0].name == "multiply"

    specs = store.get_tool_specs()
    assert len(specs) == 1
    assert specs[0](3, 4) == 12


def test_s3_skill_store_ttl_cache():
    manifest = {"version": 1, "active_skill_ids": []}
    s3_mock = _make_s3_mock({
        "arise/manifest.json": json.dumps(manifest).encode(),
    })

    store = S3SkillStore(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=60)

    # First call refreshes
    store.get_version()
    call_count = s3_mock.get_object.call_count

    # Second call within TTL uses cache
    store.get_version()
    assert s3_mock.get_object.call_count == call_count  # No new calls


def test_s3_skill_store_graceful_degradation():
    manifest = {"version": 1, "active_skill_ids": []}
    s3_mock = _make_s3_mock({
        "arise/manifest.json": json.dumps(manifest).encode(),
    })

    store = S3SkillStore(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=0)

    # Load initial state
    assert store.get_version() == 1

    # Make S3 fail
    s3_mock.get_object.side_effect = Exception("S3 unavailable")

    # Should use stale cache without raising
    assert store.get_version() == 1
    assert store.get_active_skills() == []


def test_s3_skill_store_writer():
    s3_mock = _make_s3_mock()
    writer = S3SkillStoreWriter(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=0)

    skill = Skill(
        id="w1",
        name="subtract",
        description="Subtract b from a",
        implementation="def subtract(a, b):\n    return a - b",
    )
    writer.add(skill)
    writer.promote("w1")

    assert writer.get_version() == 1
    active = writer.get_active_skills()
    assert len(active) == 1
    assert active[0].name == "subtract"

    # Deprecate
    writer.deprecate("w1", "no longer needed")
    assert writer.get_version() == 2
    assert len(writer.get_active_skills()) == 0


def test_s3_version_reload():
    """Simulate external version bump — store should reload skills."""
    skill = Skill(
        id="r1",
        name="divide",
        description="Divide",
        implementation="def divide(a, b):\n    return a / b",
        status=SkillStatus.ACTIVE,
    )
    manifest_v1 = {"version": 1, "active_skill_ids": []}
    manifest_v2 = {"version": 2, "active_skill_ids": ["r1"]}
    skill_data = _skill_to_dict(skill)

    s3_mock = _make_s3_mock({
        "arise/manifest.json": json.dumps(manifest_v1).encode(),
    })

    store = S3SkillStore(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=0)
    assert store.get_version() == 1
    assert len(store.get_active_skills()) == 0

    # Simulate external update
    s3_mock._storage["arise/manifest.json"] = json.dumps(manifest_v2).encode()
    s3_mock._storage["arise/skills/r1.json"] = json.dumps(skill_data).encode()
    # Reset side_effect since we want get_object to work normally again
    s3_mock.get_object.side_effect = None

    def get_object(Bucket, Key):
        if Key not in s3_mock._storage:
            raise Exception(f"NoSuchKey: {Key}")
        body = MagicMock()
        body.read.return_value = s3_mock._storage[Key]
        return {"Body": body}

    s3_mock.get_object = MagicMock(side_effect=get_object)

    assert store.get_version() == 2
    assert len(store.get_active_skills()) == 1


# --- SQS reporter (mocked) ---

def test_sqs_reporter_fire_and_forget():
    sqs_mock = MagicMock()
    reporter = SQSTrajectoryReporter(queue_url="https://sqs.example.com/q", sqs_client=sqs_mock)

    traj = Trajectory(task="test", outcome="ok", reward=1.0)
    reporter.report_sync(traj)

    sqs_mock.send_message.assert_called_once()
    call_kwargs = sqs_mock.send_message.call_args
    assert call_kwargs[1]["QueueUrl"] == "https://sqs.example.com/q"
    body = json.loads(call_kwargs[1]["MessageBody"])
    assert body["task"] == "test"
    assert body["reward"] == 1.0


def test_sqs_reporter_async():
    sqs_mock = MagicMock()
    reporter = SQSTrajectoryReporter(queue_url="https://sqs.example.com/q", sqs_client=sqs_mock)

    traj = Trajectory(task="async test", outcome="ok", reward=0.9)
    reporter.report(traj)

    # Give daemon thread time to complete
    time.sleep(0.2)
    sqs_mock.send_message.assert_called_once()


def test_sqs_reporter_error_swallowed(capsys):
    sqs_mock = MagicMock()
    sqs_mock.send_message.side_effect = Exception("SQS down")
    reporter = SQSTrajectoryReporter(queue_url="https://sqs.example.com/q", sqs_client=sqs_mock)

    traj = Trajectory(task="fail", outcome="", reward=0.0)
    # Should not raise
    reporter.report_sync(traj)

    captured = capsys.readouterr()
    assert "SQS send failed" in captured.err


# --- Interface checks ---

def test_interfaces():
    """Verify that concrete classes satisfy abstract interfaces."""
    assert issubclass(LocalSkillStore, SkillStoreWriter)
    assert issubclass(LocalSkillStore, SkillStore)
    assert issubclass(LocalTrajectoryReporter, TrajectoryReporter)
    assert issubclass(S3SkillStore, SkillStore)
    assert issubclass(S3SkillStoreWriter, SkillStoreWriter)
    assert issubclass(SQSTrajectoryReporter, TrajectoryReporter)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
