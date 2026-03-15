from __future__ import annotations

from arise.skills.library import SkillLibrary
from arise.stores.base import SkillStoreWriter, TrajectoryReporter
from arise.trajectory.store import TrajectoryStore
from arise.types import Skill, ToolSpec, Trajectory


class LocalSkillStore(SkillStoreWriter):
    """Wraps the existing SkillLibrary to satisfy the SkillStoreWriter interface."""

    def __init__(self, library: SkillLibrary):
        self._library = library

    def get_version(self) -> int:
        return self._library.version

    def get_active_skills(self) -> list[Skill]:
        return self._library.get_active_skills()

    def get_tool_specs(self) -> list[ToolSpec]:
        return self._library.get_tool_specs()

    def record_invocation(
        self, skill_id: str, success: bool, latency_ms: float, error: str | None = None
    ) -> None:
        self._library.record_invocation(skill_id, success, latency_ms, error)

    def add(self, skill: Skill) -> Skill:
        return self._library.add(skill)

    def promote(self, skill_id: str) -> Skill:
        return self._library.promote(skill_id)

    def deprecate(self, skill_id: str, reason: str = "") -> None:
        self._library.deprecate(skill_id, reason)

    def checkpoint(self, description: str = "") -> int:
        return self._library.checkpoint(description)

    def get_skill(self, skill_id: str) -> Skill | None:
        return self._library.get_skill(skill_id)


class LocalTrajectoryReporter(TrajectoryReporter):
    """Wraps the existing TrajectoryStore to satisfy the TrajectoryReporter interface."""

    def __init__(self, store: TrajectoryStore):
        self._store = store

    def report(self, trajectory: Trajectory) -> None:
        self._store.save(trajectory)
