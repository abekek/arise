import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise.config import ARISEConfig
from arise.skills.triggers import EvolutionTrigger
from arise.types import Trajectory, Step


def make_trajectory(reward: float, error: str | None = None) -> Trajectory:
    steps = []
    if error:
        steps.append(Step(observation="", reasoning="", action="tool", error=error))
    return Trajectory(task="test task", reward=reward, steps=steps)


def test_no_evolution_on_success():
    trigger = EvolutionTrigger(ARISEConfig(failure_threshold=3))
    trajectories = [make_trajectory(1.0) for _ in range(5)]
    assert not trigger.should_evolve(trajectories, None)


def test_evolution_on_repeated_failures():
    trigger = EvolutionTrigger(ARISEConfig(failure_threshold=3))
    trajectories = [
        make_trajectory(0.0, "NameError: name 'average' is not defined"),
        make_trajectory(0.0, "NameError: name 'average' is not defined"),
        make_trajectory(0.0, "NameError: name 'average' is not defined"),
    ]
    assert trigger.should_evolve(trajectories, None)


def test_failure_patterns():
    trigger = EvolutionTrigger(ARISEConfig())
    trajectories = [
        make_trajectory(0.0, "TypeError: cannot unpack"),
        make_trajectory(0.0, "TypeError: cannot unpack"),
        make_trajectory(0.0, "ValueError: invalid input"),
    ]
    patterns = trigger.get_failure_patterns(trajectories)
    assert len(patterns) == 1
    assert patterns[0]["count"] == 2


def test_plateau_detection():
    trigger = EvolutionTrigger(ARISEConfig(plateau_window=6, plateau_min_improvement=0.05))
    # All same reward — plateau
    trajectories = [make_trajectory(0.7) for _ in range(6)]
    assert trigger.detect_plateau(trajectories)


def test_no_plateau_when_improving():
    trigger = EvolutionTrigger(ARISEConfig(plateau_window=6, plateau_min_improvement=0.05))
    # Improving rewards (most recent first)
    trajectories = [
        make_trajectory(1.0), make_trajectory(0.9), make_trajectory(0.8),
        make_trajectory(0.3), make_trajectory(0.2), make_trajectory(0.1),
    ]
    assert not trigger.detect_plateau(trajectories)


if __name__ == "__main__":
    test_no_evolution_on_success()
    test_evolution_on_repeated_failures()
    test_failure_patterns()
    test_plateau_detection()
    test_no_plateau_when_improving()
    print("All trigger tests passed!")
