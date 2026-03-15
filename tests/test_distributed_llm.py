"""Full LLM-powered distributed test: agent fails → SQS → worker evolves → S3 → agent succeeds.

Usage:
    ARISE_TEST_BUCKET=my-bucket ARISE_TEST_QUEUE_URL=https://sqs... OPENAI_API_KEY=sk-... python tests/test_distributed_llm.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3

from arise import ARISE, ARISEConfig
from arise.stores.s3 import S3SkillStore, S3SkillStoreWriter
from arise.stores.sqs import SQSTrajectoryReporter
from arise.types import Trajectory
from arise.worker import ARISEWorker

REGION = os.environ.get("ARISE_TEST_REGION", "us-west-2")
BUCKET = os.environ.get("ARISE_TEST_BUCKET", "")
PREFIX = os.environ.get("ARISE_TEST_PREFIX", "llm-test")
QUEUE_URL = os.environ.get("ARISE_TEST_QUEUE_URL", "")
AWS_PROFILE = os.environ.get("AWS_PROFILE")

if not BUCKET or not QUEUE_URL:
    import pytest
    pytest.skip("ARISE_TEST_BUCKET and ARISE_TEST_QUEUE_URL not set", allow_module_level=True)

session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
s3 = session.client("s3")
sqs = session.client("sqs")


def cleanup():
    print("[cleanup] Removing S3 objects...")
    try:
        resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{PREFIX}/")
        for obj in resp.get("Contents", []):
            s3.delete_object(Bucket=BUCKET, Key=obj["Key"])
    except Exception:
        pass
    print("[cleanup] Draining SQS queue...")
    for _ in range(10):
        try:
            resp = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=10, WaitTimeSeconds=0)
            msgs = resp.get("Messages", [])
            if not msgs:
                break
            for msg in msgs:
                sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
        except Exception:
            break


def simple_agent(task: str, tools) -> str:
    """Agent that tries to use tools to solve tasks. No LLM — just pattern matching."""
    tool_map = {t.name: t for t in tools}

    if "hash" in task.lower() or "sha" in task.lower():
        for name, tool in tool_map.items():
            if "sha" in name.lower() or "hash" in name.lower():
                try:
                    return str(tool("hello world"))
                except Exception as e:
                    return f"Error: {e}"
        return "Error: no hashing tool available"

    if "csv" in task.lower() or "parse" in task.lower():
        for name, tool in tool_map.items():
            if "csv" in name.lower() or "parse" in name.lower():
                try:
                    return str(tool("name,age\nAlice,30\nBob,25"))
                except Exception as e:
                    return f"Error: {e}"
        return "Error: no CSV parsing tool available"

    if "base64" in task.lower() or "encode" in task.lower():
        for name, tool in tool_map.items():
            if "base64" in name.lower() or "encod" in name.lower():
                try:
                    return str(tool("hello world"))
                except Exception as e:
                    return f"Error: {e}"
        return "Error: no encoding tool available"

    return "Error: don't know how to handle this task"


def reward_fn(trajectory: Trajectory) -> float:
    outcome = trajectory.outcome.lower()
    if "error" in outcome:
        return 0.0
    return 1.0


def main():
    print("=" * 70)
    print("ARISE Distributed Mode — Full LLM-Powered Test")
    print("  Agent fails → SQS → Worker evolves (gpt-4o-mini) → S3 → Agent succeeds")
    print(f"  Bucket: {BUCKET}/{PREFIX}")
    print(f"  Queue:  {QUEUE_URL}")
    print("=" * 70)

    cleanup()

    # --- Phase 1: Agent runs tasks with no tools, fails, reports to SQS ---
    print("\n--- Phase 1: Agent fails (no tools) ---")

    store = S3SkillStore(
        bucket=BUCKET, prefix=PREFIX, region=REGION, cache_ttl=0, s3_client=s3,
    )
    # Initialize empty manifest
    writer = S3SkillStoreWriter(
        bucket=BUCKET, prefix=PREFIX, region=REGION, cache_ttl=0, s3_client=s3,
    )

    reporter = SQSTrajectoryReporter(queue_url=QUEUE_URL, region=REGION, sqs_client=sqs)

    agent = ARISE(
        agent_fn=simple_agent,
        reward_fn=reward_fn,
        skill_store=store,
        trajectory_reporter=reporter,
        config=ARISEConfig(verbose=True),
    )

    tasks = [
        "Compute the SHA-256 hash of the string 'hello world'",
        "Parse this CSV data and return the rows as a list of dicts",
        "Base64 encode the string 'hello world'",
        "Compute the SHA-256 hash of 'test input'",
        "Parse CSV with headers: name,score and data: Alice,95",
    ]

    for task in tasks:
        result = agent.run(task)
        print(f"  Result: {result[:80]}")

    # Wait for async SQS sends
    time.sleep(2)

    # --- Phase 2: Worker consumes trajectories and runs evolution ---
    print("\n--- Phase 2: Worker evolves skills (real LLM) ---")

    worker_config = ARISEConfig(
        model="gpt-4o-mini",
        s3_bucket=BUCKET,
        s3_prefix=PREFIX,
        sqs_queue_url=QUEUE_URL,
        aws_region=REGION,
        failure_threshold=3,
        max_library_size=10,
        verbose=True,
    )

    worker = ARISEWorker(
        config=worker_config,
        skill_store=writer,
        sqs_client=sqs,
    )

    # Poll until all messages consumed
    total = 0
    for _ in range(10):
        n = worker.run_once()
        total += n
        if n == 0:
            break
        time.sleep(1)

    print(f"\n  Worker consumed {total} trajectories, buffer size: {len(worker._trajectory_buffer)}")

    # Force evolution if trigger didn't fire (threshold may not have been met from single poll)
    if len(writer.get_active_skills()) == 0 and worker._trajectory_buffer:
        print("  Forcing evolution...")
        worker._evolve()

    # --- Phase 3: Check what skills were created ---
    print("\n--- Phase 3: Results ---")

    active = writer.get_active_skills()
    print(f"\n  Skills evolved: {len(active)}")
    for skill in active:
        print(f"    [{skill.origin.value}] {skill.name}: {skill.description[:80]}")

    # --- Phase 4: Agent retries with evolved tools ---
    print("\n--- Phase 4: Agent retries with evolved tools ---")

    store2 = S3SkillStore(
        bucket=BUCKET, prefix=PREFIX, region=REGION, cache_ttl=0, s3_client=s3,
    )
    agent2 = ARISE(
        agent_fn=simple_agent,
        reward_fn=reward_fn,
        skill_store=store2,
        trajectory_reporter=reporter,
        config=ARISEConfig(verbose=True),
    )

    successes = 0
    for task in tasks:
        result = agent2.run(task)
        print(f"  Result: {result[:100]}")
        if "error" not in result.lower():
            successes += 1

    print(f"\n{'=' * 70}")
    print(f"RESULTS: {successes}/{len(tasks)} tasks succeeded after evolution")
    print(f"Skills in S3: {len(store2.get_active_skills())}")
    print(f"S3 version: {store2.get_version()}")
    print("=" * 70)

    cleanup()


if __name__ == "__main__":
    main()
