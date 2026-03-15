from __future__ import annotations

from abc import ABC, abstractmethod

from arise.types import Skill, ToolSpec, Trajectory


class SkillStore(ABC):
    """Read-only skill store interface (agent side)."""

    @abstractmethod
    def get_version(self) -> int:
        ...

    @abstractmethod
    def get_active_skills(self) -> list[Skill]:
        ...

    @abstractmethod
    def get_tool_specs(self) -> list[ToolSpec]:
        ...

    def record_invocation(
        self, skill_id: str, success: bool, latency_ms: float, error: str | None = None
    ) -> None:
        """Best-effort invocation recording. No-op by default for remote stores."""


class SkillStoreWriter(SkillStore):
    """Read-write skill store interface (worker side)."""

    @abstractmethod
    def add(self, skill: Skill) -> Skill:
        ...

    @abstractmethod
    def promote(self, skill_id: str) -> Skill:
        ...

    @abstractmethod
    def deprecate(self, skill_id: str, reason: str = "") -> None:
        ...

    @abstractmethod
    def checkpoint(self, description: str = "") -> int:
        ...

    @abstractmethod
    def get_skill(self, skill_id: str) -> Skill | None:
        ...


class TrajectoryReporter(ABC):
    """Fire-and-forget trajectory reporting interface."""

    @abstractmethod
    def report(self, trajectory: Trajectory) -> None:
        """Report a trajectory. Must not block."""
        ...
