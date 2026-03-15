# ARISE — Adaptive Runtime Improvement through Self-Evolution

**Your agent works great on the tasks you planned for. ARISE handles the ones you didn't.**

ARISE is a framework-agnostic middleware that sits between your LLM agent and its tool library. When your agent encounters tasks it can't solve with its current tools, ARISE detects the gap, synthesizes a new tool, tests it in a sandbox, and promotes it to the active library — no human intervention required.

It works with any agent framework: [Strands](https://github.com/strands-agents/sdk-python), LangGraph, CrewAI, raw OpenAI/Anthropic function calling, or your own setup. ARISE doesn't replace your agent — it gives it the ability to extend itself.

## The Problem

Building an agent is easy. Maintaining its tool library is the bottleneck.

Every time your agent fails at something new, a human engineer has to:
1. Notice the failure (maybe days later, maybe never)
2. Understand what tool is missing
3. Write it, test it, deploy it

This works when you control the environment. It breaks when:
- **Your agent serves many customers** with different internal systems, APIs, and data formats
- **Your agent runs autonomously** and encounters situations you didn't anticipate at build time
- **The long tail of edge cases** isn't worth an engineer's time individually, but collectively costs you

ARISE automates the tool engineering feedback loop for these cases.

## How It Works

```mermaid
flowchart TD
    A["Your Agent — Strands, LangGraph, CrewAI, etc.
    Task → Tools → Result"] --> B["ARISE logs trajectory + computes reward"]
    B --> C{Failures accumulate?}
    C -- No --> D[Agent continues with current tools]
    C -- Yes --> E["Analyze gaps — what tool is missing?"]
    E --> F[Synthesize candidate tool via LLM]
    F --> G[Run tests in sandbox]
    G --> H[Adversarial validation]
    H --> I{Pass?}
    I -- Yes --> J[Promote to active library]
    I -- No --> K[Refine and retry]
    K --> F
    J --> A
```

## When to Use ARISE

**Use it when** your agent operates in environments you can't fully predict at build time:

- **Multi-tenant platforms** — one agent, many customers with different stacks. The agent learns each customer's API patterns and data formats.
- **Long-running autonomous agents** — ops agents, monitoring agents, data pipeline agents that encounter new situations at 3am without a human to write a quick fix.
- **Exploration agents** — agents navigating unfamiliar codebases, APIs, or datasets where the needed tools depend on what they discover.
- **Reducing tool engineering backlog** — your agent fails on 15 different edge cases. Each isn't worth an engineer's afternoon. ARISE handles the long tail.

**Don't use it when** your agent has a well-defined job with hand-crafted tools that already work. A human writing tools is faster and more reliable for known problems.

## Quick Start

```bash
pip install arise-ai
```

```python
from arise import ARISE, ToolSpec
from arise.rewards import task_success

# Your agent — any function that takes a task and tools, returns a result.
# ToolSpec gives your agent the name, description, parameter schema, and callable.
def my_agent(task: str, tools: list[ToolSpec]) -> str:
    # tools[i].name, tools[i].description — for building prompts
    # tools[i].parameters — JSON Schema for function-calling
    # tools[i].fn(...) or tools[i](...) — invoke the tool
    ...

agent = ARISE(
    agent_fn=my_agent,
    reward_fn=task_success,
    model="gpt-4o-mini",  # cheap model for tool synthesis (not your agent's model)
)

result = agent.run("Fetch all users from the paginated API and count by department")
```

## What Happens in Practice

An API integration agent starts with just `http_get` and `http_post`. It hits tasks requiring auth, pagination, and JSON parsing:

```
[ARISE] Episode 1 | FAIL | reward=0.00 | skills=2
  Task: "Fetch all paginated users with auth"
  Agent has: [http_get, http_post]

[ARISE] Episode 2 | FAIL | reward=0.00 | skills=2
[ARISE] Episode 3 | FAIL | reward=0.00 | skills=2

[ARISE] Evolution triggered — 3 failures on API tasks
[ARISE:forge] Detecting capability gaps...
[ARISE:forge] Synthesizing 'parse_json_response'...
[ARISE:forge] Testing in sandbox (attempt 1/3)... 3/3 passed
[ARISE:forge] Adversarial testing... passed
[ARISE] Skill 'parse_json_response' created and promoted!

[ARISE:forge] Synthesizing 'fetch_all_paginated'...
[ARISE:forge] Testing in sandbox (attempt 1/3)... failed
[ARISE:forge] Refining...
[ARISE:forge] Testing in sandbox (attempt 2/3)... 1/1 passed
[ARISE:forge] Adversarial testing... passed
[ARISE] Skill 'fetch_all_paginated' created and promoted!

[ARISE] Episode 4 | OK | reward=1.00 | skills=4
  Task: "Fetch analytics summary with auth"
  Agent has: [http_get, http_post, parse_json_response, fetch_all_paginated]
```

After 8 episodes, the agent autonomously created: `parse_json_response`, `fetch_all_paginated`, `count_users_by_attribute`, `calculate_total_inventory_value`, `validate_json_response`.

(See [`examples/api_agent.py`](./examples/api_agent.py) — runs a local mock API server, no external dependencies needed.)

## Strands Integration

```python
from arise import ARISE
from arise.adapters import strands_adapter
from arise.rewards import task_success
from strands.models import BedrockModel

# Wrap your Strands agent — ARISE injects evolving tools alongside your existing ones
agent_fn = strands_adapter(
    model=BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514"),
    system_prompt="You are a DevOps assistant.",
)

arise = ARISE(
    agent_fn=agent_fn,
    reward_fn=task_success,
    model="gpt-4o-mini",  # cheap model for synthesis, your agent uses Claude
)
```

ARISE uses a cheap model (gpt-4o-mini) for tool synthesis. Your agent's model is independent — use Claude, GPT-4, Gemini, whatever you want.

## Architecture

```
arise/
├── agent.py              # ARISE wrapper — the main class
├── types.py              # Skill, ToolSpec, Trajectory, GapAnalysis
├── config.py             # ARISEConfig
├── llm.py                # LLM abstraction (litellm or raw HTTP)
├── skills/
│   ├── library.py        # SQLite-backed versioned skill store
│   ├── forge.py          # Skill synthesis, refinement, adversarial testing
│   ├── sandbox.py        # Isolated execution (subprocess or Docker)
│   └── triggers.py       # When to enter evolution mode
├── trajectory/
│   ├── store.py          # Persistent trajectory logging (SQLite)
│   └── logger.py         # Per-episode trajectory recorder
├── rewards/
│   ├── builtin.py        # task_success, efficiency_reward, llm_judge, etc.
│   └── composite.py      # Combine multiple reward signals
├── prompts/              # All LLM prompts (gap detection, synthesis, etc.)
├── adapters/
│   └── strands.py        # Strands Agents SDK adapter
└── cli.py                # CLI: arise status, skills, inspect, rollback
```

## Safety Model

Generated code is not trusted by default. ARISE applies multiple validation layers before a tool enters your agent's active library:

1. **Sandbox execution** — tools run in isolated subprocesses (or Docker containers) with timeouts and resource limits
2. **Test suite generation** — the LLM writes tests alongside the tool
3. **Adversarial validation** — a separate LLM call tries to break the tool with edge cases, empty inputs, and type boundary tests
4. **Promotion gate** — only tools that pass all tests get promoted to `ACTIVE`; failures stay in `TESTING`
5. **Version control** — every mutation is versioned in SQLite; rollback anytime with `arise rollback <version>`
6. **Rate limiting** — `max_evolutions_per_hour` prevents runaway LLM costs
7. **Skills are just Python** — export and review any tool with `arise inspect <id>` or `arise export`

For production, use the Docker sandbox backend and review promoted skills before deploying.

## CLI

```bash
arise status ./skills          # Library stats: active, testing, deprecated, success rates
arise skills ./skills          # List active skills with performance metrics
arise inspect ./skills <id>    # View full implementation + test suite
arise rollback ./skills <ver>  # Rollback library to a previous version
arise export ./skills ./out    # Export skills as standalone .py files
arise history ./trajectories   # Recent trajectory outcomes
arise evolve --dry-run         # Preview what evolution would do (no LLM calls)
```

## Configuration

```python
from arise import ARISEConfig

config = ARISEConfig(
    model="gpt-4o-mini",           # LLM for tool synthesis (not your agent's model)
    sandbox_backend="subprocess",   # or "docker" for stronger isolation
    sandbox_timeout=30,             # seconds per sandbox run
    max_library_size=50,            # cap on active tools
    max_refinement_attempts=3,      # retries when generated code fails tests

    failure_threshold=5,            # failures before triggering evolution
    max_evolutions_per_hour=3,      # cost control
    max_trajectories=1000,          # auto-prune trajectory history
)
```

## API Costs

Tool synthesis uses a cheap model (gpt-4o-mini by default). Each evolution cycle is 3-5 LLM calls:
- Gap detection (~500 tokens)
- Tool synthesis (~1000 tokens)
- Adversarial test generation (~500 tokens)
- Possible refinement (~800 tokens)

**Estimated cost: $0.01-0.05 per evolution cycle.** With `max_evolutions_per_hour=3`, worst case is ~$0.15/hour. The quickstart example runs for under $0.50 total.

## Examples

| Example | What it shows |
|---------|--------------|
| [`quickstart.py`](./examples/quickstart.py) | Math agent evolves statistics tools |
| [`api_agent.py`](./examples/api_agent.py) | HTTP agent evolves auth, pagination, JSON parsing tools (local mock server) |
| [`devops_agent.py`](./examples/devops_agent.py) | DevOps agent evolves log analysis, metrics parsing tools |
| [`data_analysis_agent.py`](./examples/data_analysis_agent.py) | Data agent evolves anomaly detection, correlation tools |
| [`coding_agent.py`](./examples/coding_agent.py) | Coding agent evolves file search, code manipulation tools |
| [`retrieval_agent.py`](./examples/retrieval_agent.py) | Text agent evolves extraction, summarization tools |

## Dependencies

Core framework has **one dependency** (`pydantic`). Everything else is optional:

```
pip install arise-ai                # just pydantic
pip install arise-ai[litellm]       # + litellm for multi-provider LLM support
pip install arise-ai[docker]        # + docker for container sandbox
pip install arise-ai[all]           # everything
```

Without litellm, ARISE uses raw HTTP requests to any OpenAI-compatible API endpoint.

## Related Work

ARISE builds on ideas from several research directions:

**LLMs as Tool Makers.** [Cai et al., 2023](https://arxiv.org/abs/2305.17126) showed that LLMs can create reusable tools — a "tool maker" model generates Python functions that a cheaper "tool user" model invokes. ARISE extends this with automated testing, versioning, and a feedback loop driven by real agent failures.

**VOYAGER.** [Wang et al., 2023](https://arxiv.org/abs/2305.16291) demonstrated an open-ended agent in Minecraft that builds a skill library through exploration. ARISE applies the same skill library pattern to real-world software agents, adding sandbox validation and adversarial testing that game environments don't require.

**CREATOR.** [Qian et al., 2023](https://arxiv.org/abs/2305.14318) proposed disentangling abstract reasoning from concrete tool creation, letting LLMs create tools when existing ones are insufficient. ARISE operationalizes this with trajectory analysis to detect when creation should trigger.

**Automated Design of Agentic Systems (ADAS).** [Hu et al., 2024](https://arxiv.org/abs/2408.08435) explored meta-agents that design other agents, including their tools and prompts. ARISE focuses specifically on the tool creation component with a framework-agnostic approach.

**Toolformer.** [Schick et al., 2023](https://arxiv.org/abs/2302.04761) showed LLMs can learn *when* to use tools through self-supervised training. ARISE complements this by addressing *which* tools should exist — creating them at runtime rather than assuming a fixed toolset.

**CRAFT.** [Yuan et al., 2023](https://arxiv.org/abs/2309.17428) introduced a framework where agents create and retrieve tools from a shared library. ARISE adds the production engineering layer: sandboxed testing, adversarial validation, version control, and rollback.

## License

MIT
