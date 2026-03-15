from __future__ import annotations

from collections import Counter

from arise.config import ARISEConfig
from arise.types import Trajectory


class EvolutionTrigger:
    def __init__(self, config: ARISEConfig):
        self.config = config

    def should_evolve(self, recent_trajectories: list[Trajectory], library) -> bool:
        if not recent_trajectories:
            return False

        failures = [t for t in recent_trajectories if t.reward < 0.5]
        if len(failures) >= self.config.failure_threshold:
            return True

        if self.detect_plateau(recent_trajectories):
            return True

        return False

    def get_failure_patterns(self, trajectories: list[Trajectory]) -> list[dict]:
        error_types: Counter[str] = Counter()
        for t in trajectories:
            for step in t.steps:
                if step.error:
                    key = step.error.split("\n")[0][:100]
                    error_types[key] += 1

        patterns = []
        for error, count in error_types.most_common():
            if count >= 2:
                examples = [
                    t.task for t in trajectories
                    if any(s.error and error in (s.error.split("\n")[0][:100]) for s in t.steps)
                ]
                patterns.append({
                    "error_pattern": error,
                    "count": count,
                    "example_tasks": examples[:3],
                })
        return patterns

    def detect_plateau(self, trajectories: list[Trajectory]) -> bool:
        window = self.config.plateau_window
        if len(trajectories) < window:
            return False

        recent = trajectories[:window]
        half = window // 2
        first_half = recent[half:]
        second_half = recent[:half]

        avg_first = sum(t.reward for t in first_half) / len(first_half) if first_half else 0
        avg_second = sum(t.reward for t in second_half) / len(second_half) if second_half else 0

        improvement = avg_second - avg_first
        return improvement < self.config.plateau_min_improvement

    def detect_composition_opportunity(
        self, trajectories: list[Trajectory], library
    ) -> list[tuple[str, str]]:
        tool_sequences: Counter[tuple[str, str]] = Counter()
        for t in trajectories:
            actions = [s.action for s in t.steps if s.action != "respond"]
            for i in range(len(actions) - 1):
                pair = (actions[i], actions[i + 1])
                tool_sequences[pair] += 1

        active_names = {s.name for s in library.get_active_skills()}
        return [
            pair for pair, count in tool_sequences.most_common()
            if count >= 3 and pair[0] in active_names and pair[1] in active_names
        ]
