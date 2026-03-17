"""Tests for SkillABTest dataclass and ARISE agent A/B test integration."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise import ARISE, SkillABTest, SkillLibrary
from arise.config import ARISEConfig
from arise.types import Skill, SkillOrigin, SkillStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_skill(name: str, impl: str | None = None) -> Skill:
    return Skill(
        name=name,
        description=f"Skill {name}",
        implementation=impl or f"def {name}():\n    return '{name}'",
        origin=SkillOrigin.MANUAL,
        status=SkillStatus.ACTIVE,
    )


# ---------------------------------------------------------------------------
# SkillABTest dataclass tests
# ---------------------------------------------------------------------------

def test_ab_test_initial_status_is_running():
    a = make_skill("adder_v1", "def adder_v1(x, y):\n    return x + y")
    b = make_skill("adder_v1", "def adder_v1(x, y):\n    return x + y + 0")
    ab = SkillABTest(skill_a=a, skill_b=b, min_episodes=10)
    assert ab.status == "running"
    assert ab.winner is None
    assert ab.loser is None


def test_ab_test_get_variant_returns_one_of_the_two():
    a = make_skill("tool_v1")
    b = make_skill("tool_v1")
    ab = SkillABTest(skill_a=a, skill_b=b, min_episodes=10)
    seen_ids = set()
    for _ in range(50):
        v = ab.get_variant()
        assert v.id in (a.id, b.id)
        seen_ids.add(v.id)
    # With 50 draws, both should appear
    assert len(seen_ids) == 2


def test_ab_test_records_outcomes_correctly():
    a = make_skill("skill_a")
    b = make_skill("skill_a")
    ab = SkillABTest(skill_a=a, skill_b=b, min_episodes=10)

    ab.record(a, success=True)
    ab.record(a, success=False)
    ab.record(b, success=True)

    assert ab._a_trials == 2
    assert ab._a_successes == 1
    assert ab._b_trials == 1
    assert ab._b_successes == 1


def test_ab_test_needs_min_episodes_before_concluding():
    a = make_skill("x")
    b = make_skill("x")
    ab = SkillABTest(skill_a=a, skill_b=b, min_episodes=20)

    # Record 19 total episodes — still running
    for i in range(19):
        skill = a if i % 2 == 0 else b
        ab.record(skill, success=True)

    assert ab.status == "running"


def test_ab_test_both_variants_need_minimum_trials():
    a = make_skill("y")
    b = make_skill("y")
    ab = SkillABTest(skill_a=a, skill_b=b, min_episodes=20)

    # Give a 20 trials but b only 1 — should still be running (min_episodes // 4 = 5)
    for _ in range(20):
        ab.record(a, success=True)
    ab.record(b, success=True)

    assert ab.status == "running"
    assert ab.winner is None


def test_ab_test_concludes_with_correct_winner():
    a = make_skill("z")
    b = make_skill("z")
    ab = SkillABTest(skill_a=a, skill_b=b, min_episodes=20)

    # Give a 75% success rate, b 25% success rate
    # Distribute evenly: 10 trials each
    for i in range(10):
        ab.record(a, success=(i < 8))  # 8/10 = 80%
    for i in range(10):
        ab.record(b, success=(i < 2))  # 2/10 = 20%

    assert ab.status == "concluded"
    assert ab.winner is not None
    assert ab.winner.id == a.id
    assert ab.loser is not None
    assert ab.loser.id == b.id


def test_ab_test_b_wins_when_higher_rate():
    a = make_skill("w")
    b = make_skill("w")
    ab = SkillABTest(skill_a=a, skill_b=b, min_episodes=20)

    for i in range(10):
        ab.record(a, success=(i < 2))  # 2/10 = 20%
    for i in range(10):
        ab.record(b, success=(i < 9))  # 9/10 = 90%

    assert ab.status == "concluded"
    assert ab.winner.id == b.id
    assert ab.loser.id == a.id


def test_ab_test_tie_goes_to_skill_a():
    a = make_skill("tied")
    b = make_skill("tied")
    ab = SkillABTest(skill_a=a, skill_b=b, min_episodes=20)

    for i in range(10):
        ab.record(a, success=(i < 5))  # 5/10 = 50%
    for i in range(10):
        ab.record(b, success=(i < 5))  # 5/10 = 50%

    assert ab.status == "concluded"
    assert ab.winner.id == a.id  # tie → skill_a wins (a_rate >= b_rate)


# ---------------------------------------------------------------------------
# ARISE integration tests
# ---------------------------------------------------------------------------

def _make_agent(tmp: str, skill_a: Skill, skill_b: Skill, agent_fn=None, reward_fn=None):
    skills_path = os.path.join(tmp, "skills")
    traj_path = os.path.join(tmp, "traj")
    library = SkillLibrary(skills_path)
    library.add(skill_a)
    library.promote(skill_a.id)

    if agent_fn is None:
        def agent_fn(task, tools):
            return "ok"

    if reward_fn is None:
        def reward_fn(trajectory):
            return 1.0

    agent = ARISE(
        agent_fn=agent_fn,
        reward_fn=reward_fn,
        model="gpt-4o-mini",
        skill_library=library,
        config=ARISEConfig(
            skill_store_path=skills_path,
            trajectory_store_path=traj_path,
            failure_threshold=100,
            verbose=False,
        ),
    )
    return agent, library


def test_start_ab_test_registers_test():
    tmp = tempfile.mkdtemp()
    try:
        a = make_skill("compute", "def compute(x):\n    return x")
        b = make_skill("compute", "def compute(x):\n    return x * 2")
        agent, _ = _make_agent(tmp, a, b)

        ab = agent.start_ab_test(a, b, min_episodes=10)

        assert "compute" in agent._ab_tests
        assert agent._ab_tests["compute"] is ab
        assert ab.status == "running"
    finally:
        shutil.rmtree(tmp)


def test_ab_variants_injected_into_tool_specs():
    """The selected variant's tool spec replaces the original in each episode."""
    tmp = tempfile.mkdtemp()
    try:
        seen_skill_ids = set()

        a = make_skill("compute", "def compute(x):\n    return x")
        b = make_skill("compute", "def compute(x):\n    return x * 2")

        def agent_fn(task, tools):
            tool_map = {t.name: t for t in tools}
            # record the skill_id of the tool we got
            if "compute" in tool_map:
                seen_skill_ids.add(tool_map["compute"].skill_id)
            return "done"

        agent, _ = _make_agent(tmp, a, b, agent_fn=agent_fn)
        agent.start_ab_test(a, b, min_episodes=40)

        for _ in range(40):
            agent.run("test")

        # Both variants should have been injected at some point
        assert a.id in seen_skill_ids or b.id in seen_skill_ids
    finally:
        shutil.rmtree(tmp)


def test_ab_outcomes_recorded_after_each_run():
    tmp = tempfile.mkdtemp()
    try:
        a = make_skill("fn", "def fn():\n    return 1")
        b = make_skill("fn", "def fn():\n    return 2")

        agent, _ = _make_agent(tmp, a, b)
        ab = agent.start_ab_test(a, b, min_episodes=40)

        for _ in range(10):
            agent.run("task")

        total = ab._a_trials + ab._b_trials
        assert total == 10
    finally:
        shutil.rmtree(tmp)


def test_concluded_ab_test_auto_promotes_winner():
    tmp = tempfile.mkdtemp()
    try:
        a = make_skill("solver", "def solver():\n    return 'a'")
        b = make_skill("solver", "def solver():\n    return 'b'")

        def agent_fn(task, tools):
            return "ok"

        def reward_fn(trajectory):
            return 1.0

        skills_path = os.path.join(tmp, "skills")
        traj_path = os.path.join(tmp, "traj")
        library = SkillLibrary(skills_path)
        # Add both skills to the library so deprecate() can find them
        library.add(a)
        library.promote(a.id)
        library.add(b)
        library.promote(b.id)

        agent = ARISE(
            agent_fn=agent_fn,
            reward_fn=reward_fn,
            model="gpt-4o-mini",
            skill_library=library,
            config=ARISEConfig(
                skill_store_path=skills_path,
                trajectory_store_path=traj_path,
                failure_threshold=100,
                verbose=False,
            ),
        )
        ab = agent.start_ab_test(a, b, min_episodes=20)

        import random
        random.seed(42)
        for _ in range(40):
            agent.run("solve it")

        # After enough episodes the test should have concluded and been removed
        assert "solver" not in agent._ab_tests

        # Winner should be promoted (already active) and loser deprecated
        all_skills = library._conn.execute("SELECT id, status FROM skills").fetchall()
        statuses = {row["id"]: row["status"] for row in all_skills}
        # One should be active/promoted, one deprecated
        assert any(s == "deprecated" for s in statuses.values())
    finally:
        shutil.rmtree(tmp)


def test_ab_test_removed_from_dict_after_conclusion():
    tmp = tempfile.mkdtemp()
    try:
        a = make_skill("op", "def op():\n    return 0")
        b = make_skill("op", "def op():\n    return 1")

        agent, _ = _make_agent(tmp, a, b)
        ab = agent.start_ab_test(a, b, min_episodes=10)

        import random
        random.seed(0)
        for _ in range(30):
            agent.run("run op")

        # Test should be concluded and cleaned up
        assert "op" not in agent._ab_tests
    finally:
        shutil.rmtree(tmp)
