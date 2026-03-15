from __future__ import annotations

from arise.trajectory.store import TrajectoryStore
from arise.types import Step, Trajectory


class TrajectoryLogger:
    def __init__(self, store: TrajectoryStore, task: str, library_version: int = 0):
        self.store = store
        self.trajectory = Trajectory(
            task=task,
            skill_library_version=library_version,
        )

    def log_step(self, step: Step):
        self.trajectory.steps.append(step)

    def finalize(self, outcome: str, reward: float, metadata: dict | None = None) -> str:
        self.trajectory.outcome = outcome
        self.trajectory.reward = reward
        if metadata:
            self.trajectory.metadata.update(metadata)
        return self.store.save(self.trajectory)
