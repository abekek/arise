"""Tests for Task 4: Incremental Evolution (targeted patching)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from arise.prompts import PATCH_PROMPT
from arise.types import Skill, SkillOrigin, Trajectory, Step


# ---------------------------------------------------------------------------
# SkillOrigin enum
# ---------------------------------------------------------------------------

def test_patched_origin_exists():
    assert hasattr(SkillOrigin, "PATCHED")
    assert SkillOrigin.PATCHED.value == "patched"


def test_patched_is_distinct_from_other_origins():
    origins = {SkillOrigin.MANUAL, SkillOrigin.SYNTHESIZED, SkillOrigin.REFINED, SkillOrigin.COMPOSED}
    assert SkillOrigin.PATCHED not in origins


# ---------------------------------------------------------------------------
# PATCH_PROMPT format validation
# ---------------------------------------------------------------------------

def test_patch_prompt_has_required_placeholders():
    required = ["{name}", "{description}", "{implementation}", "{failures}"]
    for placeholder in required:
        assert placeholder in PATCH_PROMPT, f"Missing placeholder: {placeholder}"


def test_patch_prompt_formats_correctly():
    rendered = PATCH_PROMPT.format(
        name="add_numbers",
        description="Adds two integers",
        implementation="def add_numbers(a, b):\n    return a + b",
        failures="Task: add -1 and 1\nError: returned wrong sign",
    )
    assert "add_numbers" in rendered
    assert "Adds two integers" in rendered
    assert "def add_numbers" in rendered
    assert "returned wrong sign" in rendered


# ---------------------------------------------------------------------------
# forge.patch() unit tests
# ---------------------------------------------------------------------------

def _make_skill(name="my_tool", version=1, test_suite="def test_it(): pass") -> Skill:
    return Skill(
        name=name,
        description="A test tool",
        implementation=f"def {name}(x):\n    return x",
        test_suite=test_suite,
        version=version,
        origin=SkillOrigin.SYNTHESIZED,
    )


def _make_failure(task="do something", error="ValueError: bad input") -> Trajectory:
    step = Step(
        observation="called tool",
        reasoning="",
        action="my_tool",
        error=error,
    )
    t = Trajectory(task=task, outcome="failed")
    t.steps.append(step)
    return t


def _make_forge(patched_impl="def my_tool(x):\n    return x + 1"):
    """Return a SkillForge with llm_call_structured mocked."""
    from arise.skills.forge import SkillForge
    from arise.skills.sandbox import Sandbox

    sandbox = MagicMock(spec=Sandbox)
    forge = SkillForge(model="test-model", sandbox=sandbox)

    mock_response = {
        "implementation": patched_impl,
        "patch_description": "Fixed edge case for negative inputs",
    }

    with patch("arise.skills.forge.llm_call_structured", return_value=mock_response):
        yield forge, mock_response


@pytest.fixture
def forge_and_response():
    with _make_forge() as result:
        yield result


# Use a plain helper instead of contextmanager fixture to keep it simple
def test_patch_returns_patched_origin():
    from arise.skills.forge import SkillForge
    from arise.skills.sandbox import Sandbox

    sandbox = MagicMock(spec=Sandbox)
    forge = SkillForge(model="test-model", sandbox=sandbox)
    skill = _make_skill()
    failures = [_make_failure()]

    mock_resp = {
        "implementation": "def my_tool(x):\n    return abs(x)",
        "patch_description": "Use abs to fix sign bug",
    }

    with patch("arise.skills.forge.llm_call_structured", return_value=mock_resp):
        patched = forge.patch(skill, failures)

    assert patched.origin == SkillOrigin.PATCHED


def test_patch_increments_version():
    from arise.skills.forge import SkillForge
    from arise.skills.sandbox import Sandbox

    sandbox = MagicMock(spec=Sandbox)
    forge = SkillForge(model="test-model", sandbox=sandbox)
    skill = _make_skill(version=3)
    failures = [_make_failure()]

    mock_resp = {"implementation": "def my_tool(x):\n    return x", "patch_description": "no-op"}

    with patch("arise.skills.forge.llm_call_structured", return_value=mock_resp):
        patched = forge.patch(skill, failures)

    assert patched.version == 4


def test_patch_sets_parent_id():
    from arise.skills.forge import SkillForge
    from arise.skills.sandbox import Sandbox

    sandbox = MagicMock(spec=Sandbox)
    forge = SkillForge(model="test-model", sandbox=sandbox)
    skill = _make_skill()
    failures = [_make_failure()]

    mock_resp = {"implementation": "def my_tool(x):\n    return x", "patch_description": "no-op"}

    with patch("arise.skills.forge.llm_call_structured", return_value=mock_resp):
        patched = forge.patch(skill, failures)

    assert patched.parent_id == skill.id


def test_patch_preserves_name():
    from arise.skills.forge import SkillForge
    from arise.skills.sandbox import Sandbox

    sandbox = MagicMock(spec=Sandbox)
    forge = SkillForge(model="test-model", sandbox=sandbox)
    skill = _make_skill(name="special_tool")
    failures = [_make_failure()]

    mock_resp = {"implementation": "def special_tool(x):\n    return x", "patch_description": "no-op"}

    with patch("arise.skills.forge.llm_call_structured", return_value=mock_resp):
        patched = forge.patch(skill, failures)

    assert patched.name == "special_tool"


def test_patch_preserves_test_suite():
    from arise.skills.forge import SkillForge
    from arise.skills.sandbox import Sandbox

    sandbox = MagicMock(spec=Sandbox)
    forge = SkillForge(model="test-model", sandbox=sandbox)
    original_suite = "def test_my_tool():\n    assert my_tool(0) == 0"
    skill = _make_skill(test_suite=original_suite)
    failures = [_make_failure()]

    mock_resp = {"implementation": "def my_tool(x):\n    return x", "patch_description": "no-op"}

    with patch("arise.skills.forge.llm_call_structured", return_value=mock_resp):
        patched = forge.patch(skill, failures)

    assert patched.test_suite == original_suite


def test_patch_uses_new_implementation():
    from arise.skills.forge import SkillForge
    from arise.skills.sandbox import Sandbox

    sandbox = MagicMock(spec=Sandbox)
    forge = SkillForge(model="test-model", sandbox=sandbox)
    skill = _make_skill()
    failures = [_make_failure()]

    new_impl = "def my_tool(x):\n    return abs(x) if x < 0 else x"
    mock_resp = {"implementation": new_impl, "patch_description": "Handle negatives"}

    with patch("arise.skills.forge.llm_call_structured", return_value=mock_resp):
        patched = forge.patch(skill, failures)

    assert patched.implementation == new_impl


def test_patch_caps_failures_at_five():
    """forge.patch() must only pass at most 5 failures to the LLM."""
    from arise.skills.forge import SkillForge
    from arise.skills.sandbox import Sandbox

    sandbox = MagicMock(spec=Sandbox)
    forge = SkillForge(model="test-model", sandbox=sandbox)
    skill = _make_skill()
    failures = [_make_failure(task=f"task {i}") for i in range(10)]

    mock_resp = {"implementation": "def my_tool(x):\n    return x", "patch_description": "no-op"}
    captured_calls = []

    def capture_call(messages, model):
        captured_calls.append(messages[0]["content"])
        return mock_resp

    with patch("arise.skills.forge.llm_call_structured", side_effect=capture_call):
        forge.patch(skill, failures)

    # The prompt should only mention tasks 0-4 (first 5)
    content = captured_calls[0]
    assert "task 5" not in content
    assert "task 0" in content


# ---------------------------------------------------------------------------
# Integration: evolve() prefers patch over synthesis when skill exists
# ---------------------------------------------------------------------------

def test_evolve_patches_existing_skill_instead_of_synthesis():
    """When a gap's suggested_name matches an active skill, evolve() should
    call forge.patch() rather than forge.synthesize()."""
    import tempfile
    from arise.agent import ARISE
    from arise.config import ARISEConfig
    from arise.types import GapAnalysis, SandboxResult, SkillStatus

    # Build a minimal ARISE instance in local mode with isolated paths
    agent_fn = MagicMock(return_value="ok")
    reward_fn = MagicMock(return_value=0.0)

    tmpdir = tempfile.mkdtemp()
    config = ARISEConfig(skill_store_path=f"{tmpdir}/skills", trajectory_store_path=f"{tmpdir}/traj")
    arise = ARISE(agent_fn=agent_fn, reward_fn=reward_fn, config=config)

    # Create a skill that already exists in the library
    existing = Skill(
        name="existing_tool",
        description="already here",
        implementation="def existing_tool(x):\n    return x",
        test_suite="",
        status=SkillStatus.ACTIVE,
        origin=SkillOrigin.SYNTHESIZED,
    )
    arise.skill_library.add(existing)
    arise.skill_library.promote(existing.id)

    # Add a failure trajectory to the store
    failure = Trajectory(task="use existing_tool", outcome="failed", reward=0.0)
    failure.steps.append(Step(
        observation="called", reasoning="", action="existing_tool",
        error="Something went wrong",
    ))
    arise.trajectory_store.save(failure)

    # Gap that matches the existing skill name
    gap = GapAnalysis(
        description="fix existing_tool",
        suggested_name="existing_tool",
    )

    # Mock forge methods
    patched_skill = Skill(
        name="existing_tool",
        description="already here",
        implementation="def existing_tool(x):\n    return x + 1",
        version=2,
        origin=SkillOrigin.PATCHED,
        parent_id=existing.id,
    )

    sandbox_success = SandboxResult(success=True, total_passed=1, total_failed=0)

    arise.forge.detect_gaps = MagicMock(return_value=[gap])
    arise.forge.patch = MagicMock(return_value=patched_skill)
    arise.forge.synthesize = MagicMock(return_value=patched_skill)
    arise.sandbox.test_skill = MagicMock(return_value=sandbox_success)
    arise.start_ab_test = MagicMock(return_value=MagicMock())

    arise.evolve()

    # patch should be called, synthesize should NOT
    arise.forge.patch.assert_called_once()
    arise.forge.synthesize.assert_not_called()
    # A/B test should be started with the patched skill
    arise.start_ab_test.assert_called_once_with(existing, patched_skill)


def test_evolve_falls_through_to_synthesis_for_new_gaps():
    """Gaps with no existing skill should go to synthesis, not patch."""
    import tempfile
    from arise.agent import ARISE
    from arise.config import ARISEConfig
    from arise.types import GapAnalysis, SandboxResult, SkillStatus

    agent_fn = MagicMock(return_value="ok")
    reward_fn = MagicMock(return_value=0.0)

    tmpdir = tempfile.mkdtemp()
    config = ARISEConfig(skill_store_path=f"{tmpdir}/skills", trajectory_store_path=f"{tmpdir}/traj")
    arise = ARISE(agent_fn=agent_fn, reward_fn=reward_fn, config=config)

    failure = Trajectory(task="need new tool", outcome="failed", reward=0.0)
    failure.steps.append(Step(
        observation="no tool", reasoning="", action="unknown_tool", error="not found",
    ))
    arise.trajectory_store.save(failure)

    gap = GapAnalysis(
        description="brand new capability",
        suggested_name="brand_new_tool",
    )

    synthesized = Skill(
        name="brand_new_tool",
        description="brand new",
        implementation="def brand_new_tool(x):\n    return x",
        origin=SkillOrigin.SYNTHESIZED,
    )

    sandbox_success = SandboxResult(success=True, total_passed=1, total_failed=0)
    adv_result = (True, "")

    arise.forge.detect_gaps = MagicMock(return_value=[gap])
    arise.forge.patch = MagicMock(return_value=synthesized)
    arise.forge.synthesize = MagicMock(return_value=synthesized)
    arise.forge.adversarial_validate = MagicMock(return_value=adv_result)
    arise.sandbox.test_skill = MagicMock(return_value=sandbox_success)

    arise.evolve()

    arise.forge.synthesize.assert_called_once()
    arise.forge.patch.assert_not_called()
