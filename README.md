# ARISE — Self-Evolving Agent Framework

**Framework-agnostic middleware that makes any LLM agent self-improving.** Wrap your existing agent, define what "good" looks like, and ARISE handles the rest — autonomously creating, testing, versioning, and promoting new tools.

Works with **any agent framework**: Strands, LangGraph, CrewAI, raw OpenAI function calling, or your custom setup. ARISE doesn't replace your agent — it wraps it and gives it the ability to create its own tools.

## How It Works

1. Your agent runs tasks using its current tools
2. ARISE logs every trajectory and computes a reward signal
3. When failures accumulate, ARISE analyzes what tools are missing
4. It synthesizes new tools, tests them in a sandbox, validates with adversarial tests
5. Passing tools are promoted to the active library
6. Your agent now has new capabilities — automatically

## Quick Start

```bash
pip install arise-ai
```

```python
from arise import ARISE, Sandbox, SkillLibrary, ToolSpec
from arise.rewards import task_success

# Your agent — takes a task and a list of ToolSpecs, returns a result.
# ToolSpec has: name, description, parameters (JSON Schema), fn (callable)
def my_agent(task: str, tools: list[ToolSpec]) -> str:
    # Use tools[i].name, tools[i].description to decide which to call
    # Call tools[i].fn(...) or tools[i](...) to invoke
    # ... your existing agent logic ...
    pass

agent = ARISE(
    agent_fn=my_agent,
    reward_fn=task_success,
    sandbox=Sandbox(backend="subprocess"),
    skill_library=SkillLibrary("./skills"),
    model="gpt-4o-mini",  # model for skill synthesis
)

# Run tasks — agent improves over time
result = agent.run("Parse this CSV and detect anomalies")

# Check what tools the agent created
for skill in agent.skills:
    print(f"{skill.name} v{skill.version} — {skill.success_rate:.0%} success")
```

## What You'll See

```
[ARISE] Episode 1 | FAIL | reward=0.00 | skills=2
[ARISE] Episode 2 | FAIL | reward=0.00 | skills=2
[ARISE] Episode 3 | FAIL | reward=0.00 | skills=2
[ARISE] Episode 4 | FAIL | reward=0.00 | skills=2
[ARISE] Episode 5 | FAIL | reward=0.00 | skills=2
[ARISE] Evolution triggered — analyzing gaps...
[ARISE] Found 1 capability gaps.
[ARISE] Synthesizing tool: compute_statistics...
[ARISE] Testing in sandbox... 5/5 passed
[ARISE] Adversarial validation... 3/3 passed
[ARISE] Skill 'compute_statistics' created and promoted!
[ARISE] Episode 6 | OK | reward=1.00 | skills=3
```

## The ToolSpec Interface

ARISE passes your agent `ToolSpec` objects, not raw callables. This gives your agent the schema info it needs to discover and use tools:

```python
@dataclass
class ToolSpec:
    name: str              # "detect_anomalies"
    description: str       # "Detect anomalies using z-score method"
    parameters: dict       # JSON Schema for the function parameters
    fn: Callable           # The actual callable
    skill_id: str | None   # Internal tracking ID

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)
```

Your `agent_fn` receives `list[ToolSpec]` and can use `tool.name`, `tool.description`, and `tool.parameters` to build its system prompt or function-calling schema.

## Built-in Rewards

```python
from arise.rewards import (
    task_success,          # 1.0 if succeeded, 0.0 otherwise
    code_execution_reward, # Penalizes errors in tool calls
    answer_match_reward,   # Compares output to expected answer
    efficiency_reward,     # Bonus for fewer steps
    llm_judge_reward,      # LLM rates trajectory quality
    CompositeReward,       # Combine multiple rewards with weights
)

# Combine rewards
reward = CompositeReward([
    (task_success, 1.0),
    (efficiency_reward, 0.3),
])
```

## CLI

```bash
arise status ./skills          # Library statistics
arise skills ./skills          # List active skills with performance
arise inspect ./skills <id>    # View skill implementation + tests
arise rollback ./skills <ver>  # Rollback to a previous version
arise export ./skills ./out    # Export skills as standalone .py files
arise history ./trajectories   # Show recent trajectory outcomes
arise evolve --dry-run         # Preview what evolution would do
```

## Configuration

```python
from arise import ARISEConfig

config = ARISEConfig(
    model="gpt-4o-mini",           # LLM for skill synthesis
    sandbox_backend="subprocess",   # or "docker" for isolation
    sandbox_timeout=30,             # seconds
    max_library_size=50,            # max active skills
    max_refinement_attempts=3,      # retries for failing tools

    # Evolution triggers
    failure_threshold=5,            # failures before evolving
    plateau_window=10,              # episodes to detect plateau
    max_evolutions_per_hour=3,      # cost control

    # Storage
    max_trajectories=1000,          # auto-prune old trajectories
)
```

## Safety

- **Sandboxed execution**: Generated tools run in isolated subprocesses (or Docker containers) with timeouts
- **Adversarial testing**: After initial tests pass, a separate LLM call generates edge-case tests to catch bugs
- **Version control**: Every skill mutation is versioned. Rollback anytime with `arise rollback`
- **Rate limiting**: `max_evolutions_per_hour` prevents cost spirals
- **Skills are just Python**: Export and inspect any skill as a `.py` file

## API Costs

Each evolution cycle makes 3-5 LLM calls (gap detection, synthesis, test generation, possible refinement). With `gpt-4o-mini` and default settings (`max_evolutions_per_hour=3`), expect roughly **$0.01-0.05 per evolution cycle**. The quickstart example costs under $0.50 total.

Set `verbose=True` (default) to see when evolutions happen. Use `arise evolve --dry-run` to preview triggers without calling the LLM.

## Security Note

ARISE uses `exec()` to load generated skill implementations. Skills are tested in a sandbox before promotion, but once promoted, they execute in the same process as your agent. For production use:

- Review promoted skills with `arise inspect`
- Use the Docker sandbox backend for stronger isolation
- Set `allowed_imports` in config to restrict what generated code can import

## Examples

See [`examples/`](./examples/) for working demos:

- **quickstart.py** — Math agent that learns statistics tools
- **data_analysis_agent.py** — Agent that learns anomaly detection, correlation
- **coding_agent.py** — Agent that learns file search, code manipulation
- **retrieval_agent.py** — Agent that learns text extraction, summarization

## Dependencies

Core framework has **one dependency** (`pydantic`). Everything else is optional:

```
arise-ai              # just pydantic
arise-ai[litellm]     # + litellm for multi-provider LLM support
arise-ai[docker]      # + docker for container sandbox
arise-ai[all]         # everything
```

Without litellm, ARISE uses raw HTTP requests to any OpenAI-compatible API endpoint.

## License

MIT
