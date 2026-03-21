from arise.agent import ARISE
from arise.config import ARISEConfig
from arise.skills.library import SkillLibrary
from arise.skills.sandbox import Sandbox
from arise.skills.forge import SkillForge
from arise.skills.ab_test import SkillABTest
from arise.stores.base import SkillStore, SkillStoreWriter, TrajectoryReporter
from arise.types import Skill, SkillStatus, SkillOrigin, ToolSpec, Trajectory, Step, GapAnalysis, EvolutionReport
from arise.registry import SkillRegistry
from arise.llm_router import LLMRouter
from arise.rewards.learned import LearnedReward
from arise.llm import cost_tracker

__all__ = [
    "ARISE",
    "ARISEConfig",
    "SkillLibrary",
    "Sandbox",
    "SkillForge",
    "SkillABTest",
    "SkillStore",
    "SkillStoreWriter",
    "TrajectoryReporter",
    "Skill",
    "SkillStatus",
    "SkillOrigin",
    "ToolSpec",
    "Trajectory",
    "Step",
    "GapAnalysis",
    "EvolutionReport",
    "SkillRegistry",
    "LLMRouter",
    "LearnedReward",
    "cost_tracker",
]

__version__ = "0.1.3"


def create_distributed_arise(
    agent_fn,
    reward_fn,
    config: ARISEConfig | None = None,
    model: str = "gpt-4o-mini",
    **kwargs,
) -> ARISE:
    """Convenience factory for creating a distributed ARISE agent.

    Requires config.s3_bucket and config.sqs_queue_url to be set.
    """
    cfg = config or ARISEConfig(model=model)
    if not cfg.s3_bucket:
        raise ValueError("config.s3_bucket is required for distributed mode")
    if not cfg.sqs_queue_url:
        raise ValueError("config.sqs_queue_url is required for distributed mode")

    from arise.stores.s3 import S3SkillStore
    from arise.stores.sqs import SQSTrajectoryReporter

    skill_store = S3SkillStore(
        bucket=cfg.s3_bucket,
        prefix=cfg.s3_prefix,
        region=cfg.aws_region,
        cache_ttl=cfg.skill_cache_ttl_seconds,
    )
    trajectory_reporter = SQSTrajectoryReporter(
        queue_url=cfg.sqs_queue_url,
        region=cfg.aws_region,
    )

    return ARISE(
        agent_fn=agent_fn,
        reward_fn=reward_fn,
        config=cfg,
        skill_store=skill_store,
        trajectory_reporter=trajectory_reporter,
        **kwargs,
    )
