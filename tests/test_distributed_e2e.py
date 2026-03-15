"""End-to-end test of distributed mode against real AWS (S3 + SQS).

Usage:
    ARISE_TEST_BUCKET=my-bucket ARISE_TEST_QUEUE_URL=https://sqs... python tests/test_distributed_e2e.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3

from arise import ARISE, ARISEConfig
from arise.stores.s3 import S3SkillStore, S3SkillStoreWriter, _skill_to_dict
from arise.stores.sqs import SQSTrajectoryReporter, deserialize_trajectory
from arise.types import Skill, SkillOrigin, SkillStatus, Trajectory
from arise.worker import ARISEWorker

REGION = os.environ.get("ARISE_TEST_REGION", "us-west-2")
BUCKET = os.environ.get("ARISE_TEST_BUCKET", "")
PREFIX = os.environ.get("ARISE_TEST_PREFIX", "e2e-test")
QUEUE_URL = os.environ.get("ARISE_TEST_QUEUE_URL", "")
AWS_PROFILE = os.environ.get("AWS_PROFILE")

if not BUCKET or not QUEUE_URL:
    # Skip module at import time if env vars not set (pytest collection)
    import pytest
    pytest.skip("ARISE_TEST_BUCKET and ARISE_TEST_QUEUE_URL not set", allow_module_level=True)

session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
s3 = session.client("s3")
sqs = session.client("sqs")


def cleanup():
    """Remove all test objects from S3 and drain SQS queue."""
    print("[cleanup] Removing S3 objects...")
    try:
        resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{PREFIX}/")
        for obj in resp.get("Contents", []):
            s3.delete_object(Bucket=BUCKET, Key=obj["Key"])
    except Exception as e:
        print(f"  S3 cleanup: {e}")

    print("[cleanup] Draining SQS queue...")
    for _ in range(10):
        try:
            resp = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=10, WaitTimeSeconds=0)
            msgs = resp.get("Messages", [])
            if not msgs:
                break
            for msg in msgs:
                sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
        except Exception as e:
            print(f"  SQS drain: {e}")
            break


def test_s3_skill_store_writer():
    """Test: write skills to S3, read them back."""
    print("\n=== Test 1: S3SkillStoreWriter round-trip ===")

    writer = S3SkillStoreWriter(
        bucket=BUCKET, prefix=PREFIX, region=REGION, cache_ttl=0, s3_client=s3,
    )

    skill = Skill(
        id="e2e-add",
        name="add_numbers",
        description="Add two numbers",
        implementation="def add_numbers(a, b):\n    return a + b",
        test_suite="def test_add():\n    assert add_numbers(1, 2) == 3",
        origin=SkillOrigin.MANUAL,
    )

    writer.add(skill)
    writer.promote("e2e-add")

    assert writer.get_version() == 1, f"Expected version 1, got {writer.get_version()}"
    active = writer.get_active_skills()
    assert len(active) == 1, f"Expected 1 active skill, got {len(active)}"
    assert active[0].name == "add_numbers"

    specs = writer.get_tool_specs()
    assert len(specs) == 1
    assert specs[0](3, 4) == 7, "Tool invocation failed"

    print("  PASSED: Write + read + invoke skill via S3")


def test_s3_skill_store_read_only():
    """Test: read-only store picks up skills written by writer."""
    print("\n=== Test 2: S3SkillStore (read-only) reads from S3 ===")

    reader = S3SkillStore(
        bucket=BUCKET, prefix=PREFIX, region=REGION, cache_ttl=0, s3_client=s3,
    )

    assert reader.get_version() == 1
    skills = reader.get_active_skills()
    assert len(skills) == 1
    assert skills[0].name == "add_numbers"

    specs = reader.get_tool_specs()
    assert specs[0](10, 20) == 30

    print("  PASSED: Read-only store sees skills from writer")


def test_sqs_trajectory_reporter():
    """Test: send trajectory to SQS, receive it back."""
    print("\n=== Test 3: SQS trajectory round-trip ===")

    reporter = SQSTrajectoryReporter(queue_url=QUEUE_URL, region=REGION, sqs_client=sqs)

    traj = Trajectory(
        task="test e2e task",
        outcome="success",
        reward=0.9,
        skill_library_version=1,
        metadata={"source": "e2e_test"},
    )
    reporter.report_sync(traj)

    # Read it back
    time.sleep(1)
    resp = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=1, WaitTimeSeconds=5)
    messages = resp.get("Messages", [])
    assert len(messages) == 1, f"Expected 1 message, got {len(messages)}"

    restored = deserialize_trajectory(messages[0]["Body"])
    assert restored.task == "test e2e task"
    assert restored.reward == 0.9
    assert restored.metadata["source"] == "e2e_test"

    sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=messages[0]["ReceiptHandle"])
    print("  PASSED: Trajectory sent to SQS and deserialized correctly")


def test_distributed_agent():
    """Test: ARISE agent uses S3 skills and reports to SQS."""
    print("\n=== Test 4: Distributed ARISE agent ===")

    store = S3SkillStore(
        bucket=BUCKET, prefix=PREFIX, region=REGION, cache_ttl=0, s3_client=s3,
    )
    reporter = SQSTrajectoryReporter(queue_url=QUEUE_URL, region=REGION, sqs_client=sqs)

    def simple_agent(task, tools):
        tool_map = {t.name: t for t in tools}
        if "add_numbers" in tool_map:
            return str(tool_map["add_numbers"](5, 7))
        return "no tool"

    agent = ARISE(
        agent_fn=simple_agent,
        reward_fn=lambda t: 1.0,
        skill_store=store,
        trajectory_reporter=reporter,
        config=ARISEConfig(verbose=False),
    )

    result = agent.run("add 5 and 7")
    assert result == "12", f"Expected '12', got '{result}'"

    # Check trajectory was sent to SQS
    time.sleep(1)
    resp = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=1, WaitTimeSeconds=5)
    messages = resp.get("Messages", [])
    assert len(messages) == 1, f"Expected 1 trajectory in SQS, got {len(messages)}"

    restored = deserialize_trajectory(messages[0]["Body"])
    assert restored.task == "add 5 and 7"
    assert restored.reward == 1.0

    sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=messages[0]["ReceiptHandle"])
    print("  PASSED: Agent used S3 skills and reported trajectory to SQS")


def test_worker_consumes():
    """Test: worker picks up trajectories from SQS."""
    print("\n=== Test 5: Worker consumes from SQS ===")

    # Send some trajectories to SQS
    reporter = SQSTrajectoryReporter(queue_url=QUEUE_URL, region=REGION, sqs_client=sqs)
    for i in range(3):
        traj = Trajectory(task=f"worker test {i}", outcome="ok", reward=1.0)
        reporter.report_sync(traj)

    time.sleep(1)

    config = ARISEConfig(
        s3_bucket=BUCKET,
        s3_prefix=PREFIX,
        sqs_queue_url=QUEUE_URL,
        aws_region=REGION,
        failure_threshold=100,  # won't trigger evolution
        verbose=False,
    )

    store = S3SkillStoreWriter(
        bucket=BUCKET, prefix=PREFIX, region=REGION, cache_ttl=0, s3_client=s3,
    )

    worker = ARISEWorker(config=config, skill_store=store, sqs_client=sqs)

    # SQS may not return all messages in a single poll, so poll multiple times
    total_processed = 0
    for _ in range(5):
        n = worker.run_once()
        total_processed += n
        if total_processed >= 3:
            break
        time.sleep(1)

    assert total_processed >= 3, f"Expected >= 3 processed, got {total_processed}"
    assert len(worker._trajectory_buffer) >= 3
    print(f"  PASSED: Worker consumed {total_processed} trajectories from SQS")


def main():
    print("=" * 60)
    print("ARISE Distributed Mode — E2E Test (real AWS)")
    print(f"  Bucket: {BUCKET}")
    print(f"  Queue:  {QUEUE_URL}")
    print(f"  Region: {REGION}")
    print("=" * 60)

    cleanup()

    try:
        test_s3_skill_store_writer()
        test_s3_skill_store_read_only()
        test_sqs_trajectory_reporter()
        test_distributed_agent()
        test_worker_consumes()

        print("\n" + "=" * 60)
        print("ALL 5 E2E TESTS PASSED")
        print("=" * 60)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
