import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise.types import Trajectory, Step
from arise.rewards import task_success, code_execution_reward, answer_match_reward, efficiency_reward, CompositeReward


def test_task_success_with_metadata():
    t = Trajectory(task="test", metadata={"success": True})
    assert task_success(t) == 1.0

    t2 = Trajectory(task="test", metadata={"success": False})
    assert task_success(t2) == 0.0


def test_task_success_from_outcome():
    t = Trajectory(task="test", outcome="42")
    assert task_success(t) == 1.0

    t2 = Trajectory(task="test", outcome="Error: something went wrong")
    assert task_success(t2) == 0.0


def test_code_execution_reward():
    t = Trajectory(task="test", steps=[
        Step(observation="", reasoning="", action="run"),
        Step(observation="", reasoning="", action="run"),
    ])
    assert code_execution_reward(t) == 1.0

    t2 = Trajectory(task="test", steps=[
        Step(observation="", reasoning="", action="run", error="fail"),
        Step(observation="", reasoning="", action="run", error="fail2"),
    ])
    assert code_execution_reward(t2) == 0.5


def test_answer_match():
    t = Trajectory(task="test", outcome="42", metadata={"expected_output": "42"})
    assert answer_match_reward(t) == 1.0

    t2 = Trajectory(task="test", outcome="The answer is 42", metadata={"expected_output": "42"})
    assert answer_match_reward(t2) == 0.7

    t3 = Trajectory(task="test", outcome="wrong", metadata={"expected_output": "42"})
    assert answer_match_reward(t3) == 0.0


def test_efficiency():
    t0 = Trajectory(task="test", steps=[])
    assert efficiency_reward(t0) == 1.0

    t1 = Trajectory(task="test", steps=[Step(observation="", reasoning="", action="a")])
    assert efficiency_reward(t1) == 1.0

    t5 = Trajectory(task="test", steps=[Step(observation="", reasoning="", action="a")] * 5)
    assert 0.5 < efficiency_reward(t5) < 0.7


def test_composite():
    r = CompositeReward([
        (task_success, 1.0),
        (efficiency_reward, 0.5),
    ])
    t = Trajectory(task="test", metadata={"success": True}, steps=[])
    score = r(t)
    assert 0.9 < score <= 1.0


if __name__ == "__main__":
    test_task_success_with_metadata()
    test_task_success_from_outcome()
    test_code_execution_reward()
    test_answer_match()
    test_efficiency()
    test_composite()
    print("All reward tests passed!")
