from __future__ import annotations

from typing import Callable

from arise.types import Trajectory


class CompositeReward:
    def __init__(self, rewards: list[tuple[Callable[[Trajectory], float], float]]):
        self.rewards = rewards

    def __call__(self, trajectory: Trajectory) -> float:
        total_weight = sum(w for _, w in self.rewards)
        if total_weight == 0:
            return 0.0
        total = sum(fn(trajectory) * w for fn, w in self.rewards)
        return total / total_weight
