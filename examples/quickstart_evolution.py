"""
ARISE Quickstart — Evolution Loop in ~50 lines

Shows the FULL loop: agent fails at SHA-256 hashing, ARISE evolves
a compute_sha256 tool, agent succeeds on retry.

Usage:
    pip install arise-ai[litellm]
    export OPENAI_API_KEY=sk-...
    python examples/quickstart_evolution.py
"""

import os, shutil, sys, inspect, io, contextlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise import ARISE, Sandbox, SkillLibrary
from arise.config import ARISEConfig
from arise.types import Skill, SkillOrigin, SkillStatus, Trajectory


# --- Seed tool: agent can read files but NOT hash them ---
def read_file(path: str) -> str:
    """Read and return the contents of a file."""
    with open(path) as f:
        return f.read()


# --- Reward: 1.0 only if output contains a valid 64-char hex SHA-256 hash ---
def sha256_reward(trajectory: Trajectory) -> float:
    import re
    outcome = trajectory.outcome or ""
    return 1.0 if re.search(r"\b[a-f0-9]{64}\b", outcome) else 0.0


# --- Minimal agent: asks LLM to write Python using available tools ---
def agent_fn(task: str, tools: list) -> str:
    from arise.llm import llm_call

    tool_map = {t.name: t.fn for t in tools}
    tool_desc = "\n".join(f"- {t.name}: {t.description}" for t in tools)
    code = llm_call([{"role": "user", "content": (
        f"TOOLS:\n{tool_desc}\n\nTASK: {task}\n\n"
        "Write Python that calls ONLY the tools above. Print the final answer.\n"
        "If no tool fits, print 'TOOL_MISSING: <what you need>'. Code only, no markdown."
    )}], model="gpt-4o-mini")
    code = code.strip().removeprefix("```python").removeprefix("```").removesuffix("```")
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, dict(tool_map))  # noqa: S102
        return buf.getvalue().strip() or "No output"
    except Exception as e:
        return f"Error: {e}"


def main():
    # Clean up any previous runs
    for d in ["./arise_evo_demo_skills", "./arise_evo_demo_traj"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    # Create a test file to hash
    os.makedirs("/tmp/arise_demo", exist_ok=True)
    with open("/tmp/arise_demo/hello.txt", "w") as f:
        f.write("Hello, ARISE!")

    # Bootstrap with only read_file
    library = SkillLibrary("./arise_evo_demo_skills")
    skill = Skill(
        name="read_file", description="Read a file's contents",
        implementation=inspect.getsource(read_file),
        origin=SkillOrigin.MANUAL, status=SkillStatus.ACTIVE,
    )
    library.add(skill)
    library.promote(skill.id)

    agent = ARISE(
        agent_fn=agent_fn, reward_fn=sha256_reward, model="gpt-4o-mini",
        sandbox=Sandbox(backend="subprocess"),
        skill_library=library,
        config=ARISEConfig(
            model="gpt-4o-mini",
            skill_store_path="./arise_evo_demo_skills",
            trajectory_store_path="./arise_evo_demo_traj",
            failure_threshold=1,        # evolve after just 1 failure
            max_evolutions_per_hour=5,
            verbose=True,
        ),
    )

    task = "Compute the SHA-256 hash of /tmp/arise_demo/hello.txt"

    # Step 1: Agent fails — no hashing tool available
    print("=" * 60)
    print("STEP 1: Agent attempts task (should fail)")
    print("=" * 60)
    result = agent.run(task)
    print(f"Result: {result}\n")

    # Step 2: Force evolution — ARISE detects the gap and synthesizes compute_sha256
    print("=" * 60)
    print("STEP 2: ARISE evolves new tools from failure")
    print("=" * 60)
    agent.evolve()

    print("\nActive skills after evolution:")
    for s in agent.skills:
        print(f"  - {s.name} ({s.origin.value})")

    # Step 3: Agent succeeds with the new tool
    print(f"\n{'=' * 60}")
    print("STEP 3: Agent retries task (should succeed)")
    print("=" * 60)
    result = agent.run(task)
    print(f"Result: {result}")

    # Verify
    import hashlib
    expected = hashlib.sha256(b"Hello, ARISE!").hexdigest()
    print(f"\nExpected: {expected}")
    print(f"Match:    {expected in (result or '')}")


if __name__ == "__main__":
    main()
