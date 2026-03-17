"""Self-evolving DevOps agent deployed on Amazon Bedrock AgentCore.

This module is the main entry point for the ARISE DevOps demo. It wires together:
- A Strands Agent backed by Amazon Bedrock (Claude Sonnet)
- ARISE in distributed mode: S3 skill store + SQS trajectory reporter
- A Lambda/AgentCore-compatible handler

The agent starts with zero synthesized tools and evolves them over time as it
encounters tasks it cannot solve. Failed trajectories are reported to SQS;
the ARISE worker (arise/worker.py) consumes them and synthesizes new skills
into S3, which the agent picks up on the next run.

Environment variables:
    ARISE_SKILL_BUCKET  S3 bucket for the evolving skill library (required)
    ARISE_QUEUE_URL     SQS queue URL for trajectory reporting (required)
    OPENAI_API_KEY      API key used by ARISE's skill-synthesis model (required)
    AWS_REGION          AWS region (default: us-west-2)
"""

import os
import sys

from strands import Agent
from strands.models.bedrock import BedrockModel

from arise import ARISEConfig, create_distributed_arise
from arise.adapters.strands import strands_adapter
from arise.rewards.builtin import task_success

# ---------------------------------------------------------------------------
# ARISE configuration
# ---------------------------------------------------------------------------

config = ARISEConfig(
    # Cheap LLM used by ARISE to synthesize and refine tool code.
    # The agent itself uses Bedrock Claude (below).
    model="gpt-4o-mini",

    # Distributed stores — required for AgentCore / multi-instance deployments
    s3_bucket=os.environ.get("ARISE_SKILL_BUCKET", ""),
    sqs_queue_url=os.environ.get("ARISE_QUEUE_URL", ""),
    aws_region=os.environ.get("AWS_REGION", "us-west-2"),

    # Throttle to avoid runaway synthesis during bursts
    max_evolutions_per_hour=5,

    # Restrict which stdlib modules synthesized skills may import.
    # This whitelist covers all typical DevOps / data-processing tasks while
    # preventing network or subprocess access from generated code.
    allowed_imports=[
        "json",
        "csv",
        "re",
        "hashlib",
        "base64",
        "datetime",
        "math",
        "collections",
        "itertools",
        "functools",
        "pathlib",
        "os",
        "tempfile",
        "urllib",
    ],
)

# ---------------------------------------------------------------------------
# Strands Agent (the reasoning engine)
# ---------------------------------------------------------------------------

bedrock_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name=config.aws_region,
)

strands_agent = Agent(
    model=bedrock_model,
    system_prompt=(
        "You are a DevOps assistant running on Amazon Bedrock AgentCore. "
        "Use available tools to complete tasks. "
        "If no tool exists for a task, respond with: "
        "TOOL_MISSING: <describe exactly what capability you need>. "
        "Always produce clear, actionable output."
    ),
    # Silence Strands' streaming callback so it doesn't interfere with Lambda logs
    callback_handler=None,
)

# ---------------------------------------------------------------------------
# ARISE wraps the Strands agent in distributed mode
# ---------------------------------------------------------------------------

# strands_adapter converts the Strands Agent into an ARISE-compatible agent_fn.
# create_distributed_arise wires S3SkillStore + SQSTrajectoryReporter, so:
#   - Active skills are loaded from S3 on each invocation (with cache TTL)
#   - Trajectories are sent to SQS after each run for async evolution
agent_fn = strands_adapter(strands_agent)
arise = create_distributed_arise(
    agent_fn=agent_fn,
    reward_fn=task_success,
    config=config,
)

# ---------------------------------------------------------------------------
# Lambda / AgentCore entry point
# ---------------------------------------------------------------------------


def handler(event: dict, context: object = None) -> dict:
    """AgentCore / Lambda handler.

    Accepts two event shapes:
    - ``{"task": "..."}``            — direct invocation
    - ``{"body": "..."}``            — API Gateway proxy integration
    """
    task = event.get("task") or event.get("body") or ""
    if not task:
        return {"statusCode": 400, "body": "Missing 'task' in event"}

    result = arise.run(task)
    return {"statusCode": 200, "body": result}


# ---------------------------------------------------------------------------
# Local CLI runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _task = sys.argv[1] if len(sys.argv) > 1 else "Compute the SHA-256 hash of 'hello world'"
    print(arise.run(_task))
