"""Tests for EvolutionReport, evolution_history, and telemetry no-ops."""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise import ARISE, SkillLibrary
from arise.config import ARISEConfig
from arise.types import EvolutionReport, Skill, SkillOrigin, SkillStatus, Trajectory


def test_evolution_report_creation():
    report = EvolutionReport()
    assert report.gaps_detected == []
    assert report.tools_synthesized == []
    assert report.tools_promoted == []
    assert report.tools_rejected == []
    assert report.duration_ms == 0.0
    assert report.cost_usd == 0.0
    assert report.timestamp is not None


def test_evolution_report_with_data():
    report = EvolutionReport(
        gaps_detected=["parse_csv", "fetch_url"],
        tools_synthesized=["parse_csv"],
        tools_promoted=["parse_csv"],
        tools_rejected=[{"name": "fetch_url", "reason": "failed sandbox"}],
        duration_ms=1234.5,
        cost_usd=0.02,
    )
    assert len(report.gaps_detected) == 2
    assert report.tools_promoted == ["parse_csv"]
    assert report.tools_rejected[0]["reason"] == "failed sandbox"


def test_evolution_history_populated_after_evolve():
    """evolve() should append an EvolutionReport even when there are no failures."""
    tmp = tempfile.mkdtemp()
    skills_path = os.path.join(tmp, "skills")
    traj_path = os.path.join(tmp, "trajectories")

    try:
        library = SkillLibrary(skills_path)
        skill = Skill(
            name="add",
            description="Add two numbers",
            implementation="def add(a, b):\n    return a + b",
            origin=SkillOrigin.MANUAL,
            status=SkillStatus.ACTIVE,
        )
        library.add(skill)
        library.promote(skill.id)

        agent = ARISE(
            agent_fn=lambda task, tools: "ok",
            reward_fn=lambda t: 1.0,
            model="gpt-4o-mini",
            skill_library=library,
            config=ARISEConfig(
                skill_store_path=skills_path,
                trajectory_store_path=traj_path,
                failure_threshold=100,
                verbose=False,
            ),
        )

        assert agent.evolution_history == []
        assert agent.last_evolution is None

        # Run an episode so trajectory store exists, then trigger evolve
        agent.run("test task")
        agent.evolve()

        assert len(agent.evolution_history) == 1
        report = agent.last_evolution
        assert report is not None
        assert isinstance(report, EvolutionReport)
        assert report.duration_ms >= 0
    finally:
        shutil.rmtree(tmp)


def test_last_evolution_returns_most_recent():
    """last_evolution should return the most recently appended report."""
    tmp = tempfile.mkdtemp()
    skills_path = os.path.join(tmp, "skills")
    traj_path = os.path.join(tmp, "trajectories")

    try:
        library = SkillLibrary(skills_path)

        agent = ARISE(
            agent_fn=lambda task, tools: "ok",
            reward_fn=lambda t: 1.0,
            model="gpt-4o-mini",
            skill_library=library,
            config=ARISEConfig(
                skill_store_path=skills_path,
                trajectory_store_path=traj_path,
                failure_threshold=100,
                verbose=False,
            ),
        )

        agent.run("task1")
        agent.evolve()
        agent.evolve()

        assert len(agent.evolution_history) == 2
        assert agent.last_evolution is agent.evolution_history[-1]
    finally:
        shutil.rmtree(tmp)


def test_telemetry_noop_without_otel():
    """Telemetry functions should be safe no-ops when otel is not installed."""
    from arise.telemetry import add_span_attribute, end_span, start_evolution_span

    # These should not raise even without opentelemetry
    with start_evolution_span("test-span", enabled=False) as span:
        assert span is None
        add_span_attribute(span, "key", "value")
        end_span(span)

    # Also test with enabled=True but span is still None if otel not available
    with start_evolution_span("test-span", enabled=True) as span:
        add_span_attribute(span, "key", "value")
        end_span(span)


if __name__ == "__main__":
    test_evolution_report_creation()
    test_evolution_report_with_data()
    test_evolution_history_populated_after_evolve()
    test_last_evolution_returns_most_recent()
    test_telemetry_noop_without_otel()
    print("All tests passed!")
