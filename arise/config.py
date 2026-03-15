from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ARISEConfig:
    model: str = "gpt-4o-mini"
    sandbox_backend: str = "subprocess"
    sandbox_timeout: int = 30
    max_library_size: int = 50
    max_refinement_attempts: int = 3

    # Trigger thresholds
    failure_threshold: int = 5
    plateau_window: int = 10
    plateau_min_improvement: float = 0.05
    max_evolutions_per_hour: int = 3

    # Reward weights
    task_reward_weight: float = 1.0
    efficiency_bonus: float = 0.1

    # Paths
    skill_store_path: str = "./arise_skills"
    trajectory_store_path: str = "./arise_trajectories"

    # Trajectory pruning
    max_trajectories: int = 1000

    # Allowed imports in generated skills
    allowed_imports: list[str] | None = None  # None = no restriction

    # Distributed / remote store settings
    s3_bucket: str | None = None
    s3_prefix: str = "arise"
    sqs_queue_url: str | None = None
    aws_region: str = "us-east-1"
    skill_cache_ttl_seconds: int = 30

    # Logging
    verbose: bool = True
