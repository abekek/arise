"""Integration test — uses no LLM, tests the full pipeline with mock agent/forge."""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise import ARISE, SkillLibrary, Sandbox
from arise.config import ARISEConfig
from arise.types import Skill, SkillOrigin, SkillStatus, Trajectory


def test_full_pipeline():
    tmp = tempfile.mkdtemp()
    skills_path = os.path.join(tmp, "skills")
    traj_path = os.path.join(tmp, "trajectories")

    try:
        library = SkillLibrary(skills_path)

        # Add a seed skill
        skill = Skill(
            name="add",
            description="Add two numbers",
            implementation="def add(a, b):\n    return a + b",
            origin=SkillOrigin.MANUAL,
            status=SkillStatus.ACTIVE,
        )
        library.add(skill)
        library.promote(skill.id)

        # Simple agent that uses ToolSpec objects
        def simple_agent(task, tools):
            tool_map = {t.name: t for t in tools}
            if "add" in tool_map:
                return str(tool_map["add"](1, 2))
            return "no add tool"

        def always_success(trajectory):
            return 1.0

        agent = ARISE(
            agent_fn=simple_agent,
            reward_fn=always_success,
            model="gpt-4o-mini",  # won't be called
            skill_library=library,
            config=ARISEConfig(
                skill_store_path=skills_path,
                trajectory_store_path=traj_path,
                failure_threshold=100,  # never trigger evolution
                verbose=False,
            ),
        )

        result = agent.run("add 1 and 2")
        assert result == "3"

        # Check trajectory was recorded
        recent = agent.trajectory_store.get_recent(5)
        assert len(recent) == 1
        assert recent[0].reward == 1.0

        # Check stats
        stats = agent.stats
        assert stats["episodes_run"] == 1
        assert stats["active"] == 1

        # Export
        export_dir = os.path.join(tmp, "export")
        agent.export(export_dir)
        assert os.path.exists(os.path.join(export_dir, "add.py"))

        print("Integration test passed!")
    finally:
        shutil.rmtree(tmp)


def test_skill_invocation_tracking():
    tmp = tempfile.mkdtemp()
    try:
        library = SkillLibrary(os.path.join(tmp, "skills"))
        skill = Skill(
            name="double",
            description="Double a number",
            implementation="def double(x):\n    return x * 2",
            origin=SkillOrigin.MANUAL,
        )
        library.add(skill)
        library.promote(skill.id)

        def agent_fn(task, tools):
            for t in tools:
                if t.name == "double":
                    return str(t(5))
            return "no tool"

        agent = ARISE(
            agent_fn=agent_fn,
            reward_fn=lambda t: 1.0,
            skill_library=library,
            config=ARISEConfig(
                skill_store_path=os.path.join(tmp, "skills"),
                trajectory_store_path=os.path.join(tmp, "traj"),
                failure_threshold=100,
                verbose=False,
            ),
        )

        result = agent.run("double 5")
        assert result == "10"

        # Check invocation was tracked
        updated = library.get_skill(skill.id)
        assert updated.invocation_count == 1
        assert updated.success_count == 1

        print("Invocation tracking test passed!")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    test_full_pipeline()
    test_skill_invocation_tracking()
    print("All integration tests passed!")
