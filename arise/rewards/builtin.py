from __future__ import annotations

from arise.types import Trajectory


def task_success(trajectory: Trajectory) -> float:
    if trajectory.metadata.get("success"):
        return 1.0
    if trajectory.outcome and "error" not in trajectory.outcome.lower():
        return 1.0
    return 0.0


def code_execution_reward(trajectory: Trajectory) -> float:
    errors = sum(1 for s in trajectory.steps if s.error)
    if errors == 0:
        return 1.0
    return max(0.0, 1.0 - errors * 0.25)


def answer_match_reward(trajectory: Trajectory) -> float:
    expected = trajectory.metadata.get("expected_output", "")
    if not expected:
        return 0.5
    if trajectory.outcome.strip() == str(expected).strip():
        return 1.0
    if str(expected).strip().lower() in trajectory.outcome.strip().lower():
        return 0.7
    return 0.0


def efficiency_reward(trajectory: Trajectory) -> float:
    n_steps = len(trajectory.steps)
    if n_steps == 0:
        return 1.0
    return max(0.0, 1.0 - (n_steps - 1) * 0.1)


def llm_judge_reward(trajectory: Trajectory, model: str = "gpt-4o-mini") -> float:
    from arise.llm import llm_call

    steps_desc = "\n".join(
        f"- Action: {s.action}, Result: {s.result[:200]}, Error: {s.error}"
        for s in trajectory.steps
    )
    prompt = f"""\
Rate the quality of this agent trajectory on a scale of 0.0 to 1.0.

Task: {trajectory.task}
Outcome: {trajectory.outcome}
Steps:
{steps_desc}

Return ONLY a number between 0.0 and 1.0.
"""
    try:
        result = llm_call([{"role": "user", "content": prompt}], model=model)
        return max(0.0, min(1.0, float(result.strip())))
    except Exception:
        return 0.5
