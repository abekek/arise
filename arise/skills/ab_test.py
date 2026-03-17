from __future__ import annotations
import random
from dataclasses import dataclass, field
from arise.types import Skill


@dataclass
class SkillABTest:
    skill_a: Skill
    skill_b: Skill
    min_episodes: int = 20
    _a_successes: int = 0
    _a_trials: int = 0
    _b_successes: int = 0
    _b_trials: int = 0

    @property
    def status(self) -> str:
        total = self._a_trials + self._b_trials
        if total < self.min_episodes:
            return "running"
        if min(self._a_trials, self._b_trials) < self.min_episodes // 4:
            return "running"  # need data on both
        return "concluded"

    @property
    def winner(self) -> Skill | None:
        if self.status != "concluded":
            return None
        a_rate = self._a_successes / self._a_trials if self._a_trials > 0 else 0
        b_rate = self._b_successes / self._b_trials if self._b_trials > 0 else 0
        return self.skill_a if a_rate >= b_rate else self.skill_b

    @property
    def loser(self) -> Skill | None:
        w = self.winner
        if w is None:
            return None
        return self.skill_b if w.id == self.skill_a.id else self.skill_a

    def get_variant(self) -> Skill:
        return random.choice([self.skill_a, self.skill_b])

    def record(self, skill: Skill, success: bool) -> None:
        if skill.id == self.skill_a.id:
            self._a_trials += 1
            if success:
                self._a_successes += 1
        else:
            self._b_trials += 1
            if success:
                self._b_successes += 1
