"""Tests for ARISEWorker — mocked S3/SQS + SkillForge."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise.config import ARISEConfig
from arise.stores.s3 import S3SkillStoreWriter, _skill_to_dict
from arise.stores.sqs import _serialize_trajectory, deserialize_trajectory
from arise.types import GapAnalysis, Skill, SkillOrigin, SkillStatus, SandboxResult, Step, Trajectory
from arise.worker import ARISEWorker


def _make_s3_mock(objects=None):
    storage = objects or {}
    mock = MagicMock()

    def get_object(Bucket, Key):
        if Key not in storage:
            raise Exception(f"NoSuchKey: {Key}")
        body = MagicMock()
        body.read.return_value = storage[Key] if isinstance(storage[Key], bytes) else storage[Key].encode()
        return {"Body": body}

    def put_object(Bucket, Key, Body, **kwargs):
        storage[Key] = Body.encode() if isinstance(Body, str) else Body

    mock.get_object = MagicMock(side_effect=get_object)
    mock.put_object = MagicMock(side_effect=put_object)
    mock._storage = storage
    return mock


def _make_sqs_mock(messages=None):
    mock = MagicMock()
    pending = list(messages or [])

    def receive_message(QueueUrl, MaxNumberOfMessages=1, WaitTimeSeconds=0):
        batch = pending[:MaxNumberOfMessages]
        del pending[:MaxNumberOfMessages]
        return {"Messages": batch}

    mock.receive_message = MagicMock(side_effect=receive_message)
    mock.delete_message = MagicMock()
    mock._pending = pending
    return mock


def test_run_once_processes_messages():
    s3_mock = _make_s3_mock()
    config = ARISEConfig(
        s3_bucket="test-bucket",
        s3_prefix="arise",
        sqs_queue_url="https://sqs.example.com/q",
        failure_threshold=100,  # won't trigger evolution
        verbose=False,
    )

    store = S3SkillStoreWriter(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=0)

    traj = Trajectory(task="test task", outcome="ok", reward=1.0)
    body = _serialize_trajectory(traj)
    sqs_mock = _make_sqs_mock([
        {"Body": body, "ReceiptHandle": "r1"},
        {"Body": body, "ReceiptHandle": "r2"},
    ])

    worker = ARISEWorker(
        config=config,
        skill_store=store,
        sqs_client=sqs_mock,
    )

    processed = worker.run_once()
    assert processed == 2
    assert len(worker._trajectory_buffer) == 2
    assert sqs_mock.delete_message.call_count == 2


def test_run_once_triggers_evolution():
    s3_mock = _make_s3_mock()
    config = ARISEConfig(
        s3_bucket="test-bucket",
        s3_prefix="arise",
        sqs_queue_url="https://sqs.example.com/q",
        failure_threshold=2,  # Low threshold
        verbose=False,
    )

    store = S3SkillStoreWriter(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=0)

    # Create failure trajectories
    fail_trajs = []
    for i in range(5):
        t = Trajectory(
            task=f"failing task {i}",
            steps=[Step(observation="obs", reasoning="", action="act", error="something broke")],
            outcome="failed",
            reward=0.1,
        )
        fail_trajs.append({"Body": _serialize_trajectory(t), "ReceiptHandle": f"r{i}"})

    sqs_mock = _make_sqs_mock(fail_trajs)

    # Mock the forge to track if evolution was called
    mock_forge = MagicMock()
    mock_forge.detect_gaps.return_value = []  # No gaps found

    worker = ARISEWorker(
        config=config,
        skill_store=store,
        sqs_client=sqs_mock,
    )
    worker._forge = mock_forge

    worker.run_once()

    # Evolution should have been triggered
    mock_forge.detect_gaps.assert_called_once()


def test_process_trajectories_directly():
    s3_mock = _make_s3_mock()
    config = ARISEConfig(
        s3_bucket="test-bucket",
        s3_prefix="arise",
        failure_threshold=2,
        verbose=False,
    )

    store = S3SkillStoreWriter(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=0)

    mock_forge = MagicMock()
    mock_forge.detect_gaps.return_value = []

    worker = ARISEWorker(config=config, skill_store=store)
    worker._forge = mock_forge

    trajs = [
        Trajectory(task="t1", outcome="fail", reward=0.1),
        Trajectory(task="t2", outcome="fail", reward=0.2),
        Trajectory(task="t3", outcome="fail", reward=0.1),
    ]
    worker.process_trajectories(trajs)

    mock_forge.detect_gaps.assert_called_once()


def test_evolution_promotes_skill():
    """Full evolution cycle: gap detected → skill synthesized → promoted to S3."""
    s3_mock = _make_s3_mock()
    config = ARISEConfig(
        s3_bucket="test-bucket",
        s3_prefix="arise",
        failure_threshold=1,
        verbose=False,
    )

    store = S3SkillStoreWriter(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=0)

    new_skill = Skill(
        id="evolved1",
        name="smart_calc",
        description="Smart calculator",
        implementation="def smart_calc(expr):\n    return eval(expr)",
    )

    mock_forge = MagicMock()
    mock_forge.detect_gaps.return_value = [
        GapAnalysis(description="Need calculator", suggested_name="smart_calc"),
    ]
    mock_forge.synthesize.return_value = new_skill

    mock_sandbox = MagicMock()
    mock_sandbox.test_skill.return_value = SandboxResult(success=True)
    mock_forge.adversarial_validate.return_value = (True, "")

    worker = ARISEWorker(config=config, skill_store=store, sandbox=mock_sandbox)
    worker._forge = mock_forge

    # Feed failure trajectories
    worker._trajectory_buffer = [
        Trajectory(task="calc 1+1", outcome="fail", reward=0.0),
        Trajectory(task="calc 2+2", outcome="fail", reward=0.0),
    ]

    worker._evolve()

    # Skill should be in S3
    active = store.get_active_skills()
    assert len(active) == 1
    assert active[0].name == "smart_calc"
    assert store.get_version() == 1


def test_buffer_capping():
    s3_mock = _make_s3_mock()
    config = ARISEConfig(
        s3_bucket="test-bucket",
        s3_prefix="arise",
        failure_threshold=1000,  # Won't trigger
        verbose=False,
    )

    store = S3SkillStoreWriter(bucket="test-bucket", prefix="arise", s3_client=s3_mock, cache_ttl=0)
    worker = ARISEWorker(config=config, skill_store=store, max_buffer_size=5)

    trajs = [Trajectory(task=f"t{i}", reward=1.0) for i in range(10)]
    worker.process_trajectories(trajs)

    assert len(worker._trajectory_buffer) == 5


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
