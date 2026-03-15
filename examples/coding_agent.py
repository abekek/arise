"""
ARISE Example — Coding Agent

Agent starts with basic file tools and learns code manipulation tools.

Usage:
    export OPENAI_API_KEY=sk-...
    python examples/coding_agent.py
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise import ARISE, Sandbox, SkillLibrary
from arise.config import ARISEConfig
from arise.rewards import task_success
from arise.types import Skill, SkillOrigin, SkillStatus


def read_file(path: str) -> str:
    """Read the contents of a file."""
    try:
        with open(path) as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Written to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_command(cmd: str) -> str:
    """Run a shell command and return stdout + stderr."""
    import subprocess
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"
        return output.strip() or "(no output)"
    except Exception as e:
        return f"Error: {e}"


def coding_agent(task: str, tools: list) -> str:
    from arise.llm import llm_call

    tool_map = {}
    descs = []
    for t in tools:
        tool_map[t.name] = t.fn
        descs.append(f"- {t.name}: {t.description}")

    prompt = f"""\
You are a coding agent. Complete the task using the tools.

TOOLS:
{chr(10).join(descs)}

TASK: {task}

Write Python code calling the tools. Print the result.
Return ONLY Python code."""

    code = llm_call([{"role": "user", "content": prompt}], model="gpt-4o-mini")
    code = code.strip().removeprefix("```python").removeprefix("```").removesuffix("```").strip()

    import io, contextlib
    buf = io.StringIO()
    namespace = dict(tool_map)
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, namespace)  # noqa: S102
        return buf.getvalue().strip() or "Done"
    except Exception as e:
        return f"Error: {e}"


def main():
    for d in ["./arise_skills_code", "./arise_trajectories_code"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    library = SkillLibrary("./arise_skills_code")

    for fn, desc in [
        (read_file, "Read file contents"),
        (write_file, "Write content to a file"),
        (run_command, "Run a shell command"),
    ]:
        import inspect
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
        agent_fn=coding_agent,
        reward_fn=task_success,
        model="gpt-4o-mini",
        skill_library=library,
        config=ARISEConfig(
            skill_store_path="./arise_skills_code",
            trajectory_store_path="./arise_trajectories_code",
            failure_threshold=2,
            verbose=True,
        ),
    )

    tasks = [
        "Create a Python file /tmp/arise_demo/hello.py that prints 'Hello World' and run it",
        "Search for all .py files in /tmp/arise_demo and list them",
        "Count the lines of code in /tmp/arise_demo/hello.py",
        "Create a function in /tmp/arise_demo/utils.py that reverses a string, then test it",
    ]

    print("ARISE Coding Agent Demo")
    print("=" * 60)
    for i, task in enumerate(tasks):
        print(f"\nTask {i + 1}: {task}")
        result = agent.run(task)
        print(f"Result: {result}")

    print(f"\nFinal skills: {[s.name for s in agent.skills]}")


if __name__ == "__main__":
    main()
