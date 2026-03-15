"""
ARISE Example — Data Analysis Agent

Agent starts with basic tools and learns specialized data analysis tools
like anomaly detection, correlation matrices, and summary statistics.

Usage:
    export OPENAI_API_KEY=sk-...
    python examples/data_analysis_agent.py
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise import ARISE, Sandbox, SkillLibrary
from arise.config import ARISEConfig
from arise.rewards import CompositeReward, task_success, efficiency_reward
from arise.types import Skill, SkillOrigin, SkillStatus


# --- Seed tools ---

def read_csv(filepath: str) -> str:
    """Read a CSV file and return its contents as a string representation."""
    import csv
    import io
    try:
        with open(filepath) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            return "Empty CSV"
        header = ", ".join(rows[0].keys())
        data_rows = [", ".join(str(v) for v in row.values()) for row in rows[:20]]
        return f"Columns: {header}\nRows ({len(rows)} total):\n" + "\n".join(data_rows)
    except Exception as e:
        return f"Error reading CSV: {e}"


def pandas_query(code: str) -> str:
    """Execute a pandas query/operation and return the result."""
    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, {"__builtins__": __builtins__})  # noqa: S102
        return buf.getvalue().strip() or "Done (no output)"
    except Exception as e:
        return f"Error: {e}"


# --- Agent ---

def data_agent(task: str, tools: list) -> str:
    from arise.llm import llm_call

    tool_descriptions = []
    tool_map = {}
    for t in tools:
        tool_descriptions.append(f"- {t.name}: {t.description}")
        tool_map[t.name] = t.fn

    prompt = f"""\
You are a data analysis agent. Solve the task using the available tools.

TOOLS:
{chr(10).join(tool_descriptions)}

TASK: {task}

Write Python code using the tools as functions. Print the final answer.
Return ONLY Python code."""

    code = llm_call([{"role": "user", "content": prompt}], model="gpt-4o-mini")
    code = code.strip().removeprefix("```python").removeprefix("```").removesuffix("```").strip()

    import io
    import contextlib
    namespace = dict(tool_map)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, namespace)  # noqa: S102
        return buf.getvalue().strip() or "No output"
    except Exception as e:
        return f"Error: {e}"


def main():
    for d in ["./arise_skills_data", "./arise_trajectories_data"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    library = SkillLibrary("./arise_skills_data")

    for fn, desc in [
        (read_csv, "Read a CSV file and return its contents"),
        (pandas_query, "Execute pandas code and return results"),
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

    reward = CompositeReward([
        (task_success, 1.0),
        (efficiency_reward, 0.3),
    ])

    agent = ARISE(
        agent_fn=data_agent,
        reward_fn=reward,
        model="gpt-4o-mini",
        sandbox=Sandbox(),
        skill_library=library,
        config=ARISEConfig(
            skill_store_path="./arise_skills_data",
            trajectory_store_path="./arise_trajectories_data",
            failure_threshold=2,
            verbose=True,
        ),
    )

    tasks = [
        "Calculate the mean and standard deviation of the numbers [23, 45, 12, 67, 34, 89, 56]",
        "Find anomalies in the dataset [10, 12, 11, 13, 100, 11, 12, 10, 99, 13] using z-score method",
        "Compute the correlation between [1,2,3,4,5] and [2,4,5,4,5]",
        "Generate summary statistics (min, max, mean, median, std) for [5, 10, 15, 20, 25, 30]",
        "Detect outliers in [1, 2, 3, 2, 1, 50, 2, 3, 1, 2] using IQR method",
    ]

    print("ARISE Data Analysis Agent Demo")
    print("=" * 60)

    for i, task in enumerate(tasks):
        print(f"\nTask {i + 1}: {task}")
        result = agent.run(task)
        print(f"Result: {result}")

    print(f"\nFinal skills: {[s.name for s in agent.skills]}")


if __name__ == "__main__":
    main()
