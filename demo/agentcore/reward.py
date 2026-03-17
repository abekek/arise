"""Task-specific reward function for the ARISE DevOps agent demo.

Reward logic (in priority order):
1. If the trajectory's metadata contains 'expected_pattern', apply regex matching
   against the agent's outcome:
       - 1.0  if the pattern matches (success)
       - 0.0  if there is no match or the outcome indicates an error
2. Otherwise fall back to ``arise.rewards.builtin.task_success``, which returns
   1.0 when the trajectory has no error indicators.

This two-tier approach lets individual tasks supply precise correctness criteria
while still providing a reasonable default for open-ended tasks.
"""

from __future__ import annotations

import re

from arise.rewards.builtin import task_success
from arise.types import Trajectory


def devops_reward(trajectory: Trajectory) -> float:
    """Score a DevOps agent trajectory.

    Args:
        trajectory: The completed agent trajectory, including outcome text and
            any task metadata set by the caller (e.g. ``expected_pattern``).

    Returns:
        A float in [0.0, 1.0]:
            1.0 — task completed correctly
            0.0 — task failed or output does not match the expected pattern
    """
    outcome = trajectory.outcome or ""

    # Short-circuit on explicit error indicators
    if not outcome:
        return 0.0
    if outcome.strip().lower().startswith("error"):
        return 0.0
    if "TOOL_MISSING" in outcome:
        # Agent signalled it lacks the required capability — low reward so ARISE
        # treats this as a gap and synthesizes a new tool
        return 0.0

    # --- Pattern-based scoring ---
    pattern: str | None = trajectory.metadata.get("expected_pattern")
    if pattern:
        try:
            match = re.search(pattern, outcome, re.IGNORECASE | re.DOTALL)
            return 1.0 if match else 0.0
        except re.error:
            # Malformed pattern — fall through to default scorer
            pass

    # --- Default: delegate to ARISE's built-in heuristic ---
    return task_success(trajectory)
