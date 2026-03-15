"""
ARISE Example — Retrieval Agent

Agent starts with basic search tools and learns extraction/summarization tools.

Usage:
    export OPENAI_API_KEY=sk-...
    python examples/retrieval_agent.py
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise import ARISE, Sandbox, SkillLibrary
from arise.config import ARISEConfig
from arise.rewards import task_success
from arise.types import Skill, SkillOrigin, SkillStatus


def search_text(text: str, query: str) -> str:
    """Search for lines in text that contain the query string (case-insensitive)."""
    results = [line for line in text.split("\n") if query.lower() in line.lower()]
    return "\n".join(results) if results else "No matches found"


def extract_pattern(text: str, pattern: str) -> str:
    """Extract all regex matches from text."""
    import re
    matches = re.findall(pattern, text)
    return "\n".join(str(m) for m in matches) if matches else "No matches"


def retrieval_agent(task: str, tools: list) -> str:
    from arise.llm import llm_call

    tool_map = {t.name: t.fn for t in tools}
    descs = [f"- {t.name}: {t.description}" for t in tools]

    prompt = f"""\
You are a text retrieval and extraction agent.

TOOLS:
{chr(10).join(descs)}

TASK: {task}

Write Python code using the tools. Print the result.
Return ONLY Python code."""

    code = llm_call([{"role": "user", "content": prompt}], model="gpt-4o-mini")
    code = code.strip().removeprefix("```python").removeprefix("```").removesuffix("```").strip()

    import io, contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, {**tool_map, "__builtins__": __builtins__})  # noqa: S102
        return buf.getvalue().strip() or "No output"
    except Exception as e:
        return f"Error: {e}"


def main():
    for d in ["./arise_skills_retrieval", "./arise_trajectories_retrieval"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    library = SkillLibrary("./arise_skills_retrieval")

    for fn, desc in [
        (search_text, "Search for lines containing a query"),
        (extract_pattern, "Extract regex matches from text"),
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
        agent_fn=retrieval_agent,
        reward_fn=task_success,
        model="gpt-4o-mini",
        skill_library=library,
        config=ARISEConfig(
            skill_store_path="./arise_skills_retrieval",
            trajectory_store_path="./arise_trajectories_retrieval",
            failure_threshold=2,
            verbose=True,
        ),
    )

    sample_text = """
Name: Alice, Age: 30, Email: alice@example.com, Role: Engineer
Name: Bob, Age: 25, Email: bob@test.org, Role: Designer
Name: Charlie, Age: 35, Email: charlie@example.com, Role: Manager
Name: Diana, Age: 28, Email: diana@corp.io, Role: Engineer
"""

    tasks = [
        f"Extract all email addresses from this text:\n{sample_text}",
        f"Find all engineers in this data:\n{sample_text}",
        f"Extract names and ages as a structured list from:\n{sample_text}",
        f"Calculate the average age from this data:\n{sample_text}",
    ]

    print("ARISE Retrieval Agent Demo")
    print("=" * 60)
    for i, task in enumerate(tasks):
        print(f"\nTask {i + 1}: {task[:80]}...")
        result = agent.run(task)
        print(f"Result: {result}")

    print(f"\nFinal skills: {[s.name for s in agent.skills]}")


if __name__ == "__main__":
    main()
