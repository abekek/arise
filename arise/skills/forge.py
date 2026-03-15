from __future__ import annotations

import sys

from arise.llm import llm_call_structured, llm_call


def _log(msg: str):
    print(f"[ARISE:forge] {msg}", flush=True)
from arise.prompts import (
    ADVERSARIAL_TEST_PROMPT,
    GAP_DETECTION_PROMPT,
    SYNTHESIS_PROMPT,
    TEST_GENERATION_PROMPT,
    REFINEMENT_PROMPT,
)
from arise.skills.sandbox import Sandbox
from arise.types import GapAnalysis, Skill, SkillOrigin, SkillStatus, Trajectory


class SkillForge:
    def __init__(self, model: str, sandbox: Sandbox, max_retries: int = 3):
        self.model = model
        self.sandbox = sandbox
        self.max_retries = max_retries

    def detect_gaps(
        self,
        failed_trajectories: list[Trajectory],
        library,  # SkillLibrary — avoid circular import
    ) -> list[GapAnalysis]:
        active = library.get_active_skills()
        tools_desc = "\n".join(
            f"- {s.name}: {s.description}" for s in active
        ) or "(none)"

        traj_desc = "\n\n".join(
            f"Task: {t.task}\nOutcome: {t.outcome}\nReward: {t.reward}\nSteps:\n"
            + "\n".join(
                f"  - Action: {s.action}, Error: {s.error}" for s in t.steps
            )
            for t in failed_trajectories[:10]
        )

        prompt = GAP_DETECTION_PROMPT.format(
            trajectories=traj_desc,
            existing_tools=tools_desc,
        )

        _log("Detecting capability gaps...")
        raw = llm_call_structured(
            [{"role": "user", "content": prompt}],
            model=self.model,
        )

        if isinstance(raw, list):
            return [GapAnalysis(**g) for g in raw]
        return []

    def synthesize(
        self,
        gap: GapAnalysis,
        library,
        example_trajectories: list[Trajectory] | None = None,
    ) -> Skill:
        active = library.get_active_skills()
        tools_desc = "\n".join(
            f"- {s.name}: {s.description}" for s in active
        ) or "(none)"

        evidence = "\n".join(gap.evidence) if gap.evidence else "(none)"

        prompt = SYNTHESIS_PROMPT.format(
            description=gap.description,
            signature=gap.suggested_signature,
            existing_tools=tools_desc,
            evidence=evidence,
        )

        _log(f"Synthesizing '{gap.suggested_name}'...")
        raw = llm_call_structured(
            [{"role": "user", "content": prompt}],
            model=self.model,
        )

        skill = Skill(
            name=raw["name"],
            description=raw.get("description", gap.description),
            implementation=raw["implementation"],
            test_suite=raw.get("test_suite", ""),
            origin=SkillOrigin.SYNTHESIZED,
        )

        # Validate in sandbox, refine if needed
        for attempt in range(self.max_retries):
            _log(f"Testing in sandbox (attempt {attempt + 1}/{self.max_retries})...")
            result = self.sandbox.test_skill(skill)
            if result.success:
                _log(f"All {result.total_passed} tests passed!")
                return skill

            errors = "\n".join(
                f"{t.test_name}: {t.error}" for t in result.test_results if not t.passed
            )
            if result.stderr:
                errors += f"\nStderr: {result.stderr}"

            _log(f"Tests failed ({result.total_failed} failures), refining...")
            skill = self.refine(skill, errors)

        return skill

    def refine(self, skill: Skill, feedback: str) -> Skill:
        _log(f"Refining '{skill.name}'...")
        prompt = REFINEMENT_PROMPT.format(
            name=skill.name,
            description=skill.description,
            implementation=skill.implementation,
            test_suite=skill.test_suite,
            feedback=feedback,
        )

        raw = llm_call_structured(
            [{"role": "user", "content": prompt}],
            model=self.model,
        )

        return Skill(
            name=skill.name,
            description=skill.description,
            implementation=raw["implementation"],
            test_suite=raw.get("test_suite", skill.test_suite),
            version=skill.version + 1,
            origin=SkillOrigin.REFINED,
            parent_id=skill.id,
        )

    def compose(self, skill_a: Skill, skill_b: Skill, description: str) -> Skill:
        prompt = f"""\
Combine these two Python tools into a single higher-level tool.

TOOL A — {skill_a.name}:
```python
{skill_a.implementation}
```

TOOL B — {skill_b.name}:
```python
{skill_b.implementation}
```

DESIRED BEHAVIOR:
{description}

Create a new function that uses both tools. Include the implementations of both tools in the output.

Return ONLY a JSON object:
{{
    "name": "composed_function_name",
    "description": "One-line description",
    "implementation": "full Python source code including both original functions and the new composed function",
    "test_suite": "test code with test_* functions"
}}
"""

        raw = llm_call_structured(
            [{"role": "user", "content": prompt}],
            model=self.model,
        )

        skill = Skill(
            name=raw["name"],
            description=raw.get("description", description),
            implementation=raw["implementation"],
            test_suite=raw.get("test_suite", ""),
            origin=SkillOrigin.COMPOSED,
        )

        # Validate
        result = self.sandbox.test_skill(skill)
        if not result.success:
            errors = "\n".join(
                f"{t.test_name}: {t.error}" for t in result.test_results if not t.passed
            )
            skill = self.refine(skill, errors)

        return skill

    def adversarial_validate(self, skill: Skill) -> tuple[bool, str]:
        """Run adversarial tests against a skill. Returns (passed, feedback)."""
        _log(f"Adversarial testing '{skill.name}'...")
        prompt = ADVERSARIAL_TEST_PROMPT.format(
            name=skill.name,
            description=skill.description,
            implementation=skill.implementation,
            existing_tests=skill.test_suite,
        )
        adv_tests = llm_call(
            [{"role": "user", "content": prompt}],
            model=self.model,
        )
        adv_tests = adv_tests.strip()
        if adv_tests.startswith("```"):
            lines = adv_tests.split("\n")
            adv_tests = "\n".join(l for l in lines[1:] if l.strip() != "```")

        # Create a skill copy with combined tests
        combined = Skill(
            name=skill.name,
            implementation=skill.implementation,
            test_suite=skill.test_suite + "\n\n" + adv_tests,
        )
        result = self.sandbox.test_skill(combined)
        if result.success:
            # Merge adversarial tests into the skill's test suite
            skill.test_suite = combined.test_suite
            return True, ""
        else:
            failures = "\n".join(
                f"{t.test_name}: {t.error}" for t in result.test_results if not t.passed
            )
            return False, failures

    def generate_tests(self, skill: Skill, num_tests: int = 5) -> str:
        prompt = TEST_GENERATION_PROMPT.format(
            name=skill.name,
            description=skill.description,
            implementation=skill.implementation,
            num_tests=num_tests,
        )

        return llm_call(
            [{"role": "user", "content": prompt}],
            model=self.model,
        )
