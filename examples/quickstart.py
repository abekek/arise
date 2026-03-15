"""
ARISE Quickstart — Math Tool Agent

Agent starts with `add` and `multiply` tools. Give it tasks that require
`average`, `std_dev`, `factorial`, etc. Watch it create those tools.

Usage:
    export OPENAI_API_KEY=sk-...
    python examples/quickstart.py
"""

import os
import shutil
import sys
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise import ARISE, Sandbox, SkillLibrary
from arise.config import ARISEConfig
from arise.types import Skill, SkillOrigin, SkillStatus, Trajectory


# --- Seed tools ---

def add(a, b):
    """Add two numbers together. Returns a + b."""
    return float(a) + float(b)


def multiply(a, b):
    """Multiply two numbers together. Returns a * b."""
    return float(a) * float(b)


# --- Reward: succeed only if the agent used at least one tool ---

def tool_usage_reward(trajectory: Trajectory) -> float:
    """1.0 only if the agent called a tool AND produced a result without errors."""
    has_error = "error" in trajectory.outcome.lower() if trajectory.outcome else True
    tool_calls = [s for s in trajectory.steps if s.action not in ("respond", "error")]
    used_tools = len(tool_calls) > 0
    if has_error:
        return 0.0
    if not used_tools:
        return 0.2  # Got answer but didn't use tools — low reward
    return 1.0


# --- Simple agent that uses tools ---

def math_agent(task: str, tools: list) -> str:
    from arise.llm import llm_call

    tool_descriptions = []
    tool_map = {}
    for t in tools:
        params = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in t.parameters.get("properties", {}).items())
        tool_descriptions.append(f"- {t.name}({params}): {t.description}")
        tool_map[t.name] = t.fn

    tools_text = "\n".join(tool_descriptions) if tool_descriptions else "(no tools available)"

    prompt = f"""\
You are a math agent. You MUST solve the task by calling the provided tools.

AVAILABLE TOOLS:
{tools_text}

TASK: {task}

CRITICAL RULES:
- You MUST use ONLY the provided tool functions. Do NOT use Python builtins like sum(), len(), math.*, etc.
- If no tool can solve the task, print "TOOL_MISSING: <describe what tool you need>"
- Compose multiple tool calls if needed (e.g., use add() in a loop to sum a list)

Write Python code that calls the tools. Print the final answer.
Return ONLY Python code, no markdown."""

    code = llm_call([{"role": "user", "content": prompt}], model="gpt-4o-mini")
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(l for l in lines[1:] if l.strip() != "```")

    namespace = dict(tool_map)
    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, namespace)  # noqa: S102
        output = buf.getvalue().strip()
        return output if output else "No output"
    except Exception as e:
        return f"Error: {e}"


def main():
    for d in ["./arise_skills_demo", "./arise_trajectories_demo"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    library = SkillLibrary("./arise_skills_demo")
    sandbox = Sandbox(backend="subprocess")

    for fn, desc in [(add, "Add two numbers"), (multiply, "Multiply two numbers")]:
        skill = Skill(
            name=fn.__name__,
            description=desc,
            implementation=inspect.getsource(fn),
            origin=SkillOrigin.MANUAL,
            status=SkillStatus.ACTIVE,
        )
        library.add(skill)
        library.promote(skill.id)

    agent = ARISE(
        agent_fn=math_agent,
        reward_fn=tool_usage_reward,
        model="gpt-4o-mini",
        sandbox=sandbox,
        skill_library=library,
        config=ARISEConfig(
            model="gpt-4o-mini",
            skill_store_path="./arise_skills_demo",
            trajectory_store_path="./arise_trajectories_demo",
            failure_threshold=3,
            max_evolutions_per_hour=5,
            verbose=True,
        ),
    )

    tasks = [
        "Calculate 15 + 27",
        "Calculate 6 * 8",
        "Calculate the average of [10, 20, 30, 40, 50]",
        "Calculate the factorial of 7",
        "Calculate the standard deviation of [2, 4, 4, 4, 5, 5, 7, 9]",
        "Find the greatest common divisor of 48 and 18",
        "Calculate 2 raised to the power of 10",
        "Calculate the average of [100, 200, 300]",
        "Calculate the factorial of 5",
        "Calculate the standard deviation of [1, 2, 3, 4, 5]",
    ]

    print("=" * 60)
    print("ARISE Quickstart — Math Agent Self-Evolution Demo")
    print("=" * 60)

    for i, task in enumerate(tasks):
        print(f"\n{'=' * 60}")
        print(f"Task {i + 1}: {task}")
        print("-" * 60)
        result = agent.run(task)
        print(f"Result: {result}")

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    stats = agent.stats
    print(f"Episodes run:         {stats['episodes_run']}")
    print(f"Active skills:        {stats['active']}")
    print(f"Recent success rate:  {stats['recent_success_rate']:.1%}")

    print("\nActive Skills:")
    for skill in agent.skills:
        print(f"  - {skill.name} (v{skill.version}, {skill.origin.value}, {skill.success_rate:.0%} success)")

    agent.export("./arise_skills_demo/exported")
    print(f"\nSkills exported to ./arise_skills_demo/exported/")


if __name__ == "__main__":
    main()
