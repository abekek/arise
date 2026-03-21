# ARISE — Adaptive Runtime Improvement through Self-Evolution

[![PyPI version](https://img.shields.io/pypi/v/arise-ai.svg)](https://pypi.org/project/arise-ai/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://pypi.org/project/arise-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Your agent works great on the tasks you planned for. ARISE handles the ones you didn't.**

ARISE is a framework-agnostic middleware that gives LLM agents the ability to create their own tools at runtime. When your agent fails at a task, ARISE detects the capability gap, synthesizes a Python tool, validates it in a sandbox, and promotes it to the active library — no human intervention required.

```bash
pip install arise-ai
```

```python
from arise import ARISE
from arise.rewards import task_success

arise = ARISE(
    agent_fn=my_agent,           # any (task, tools) -> str function
    reward_fn=task_success,
    model="gpt-4o-mini",         # cheap model for tool synthesis
)

result = arise.run("Fetch all users from the paginated API")
# Agent fails → ARISE synthesizes fetch_all_paginated tool → agent succeeds
```

---

## How It Works

```mermaid
flowchart TD
    A["Agent receives task"] --> B["Execute with current tools"]
    B --> C{"Success?"}
    C -- "Yes (reward ≥ 0.5)" --> D["Log trajectory, continue"]
    C -- "No (reward < 0.5)" --> E["Log failure trajectory"]
    E --> F{"Enough failures?"}
    F -- No --> D
    F -- Yes --> G["Detect capability gaps"]
    G --> H["Synthesize new tool via LLM"]
    H --> I["Test in sandbox + adversarial validation"]
    I --> J{"Pass?"}
    J -- Yes --> K["Promote to active library"]
    J -- No --> L["Refine and retry"]
    L --> H
    K --> A

    style G fill:#f9d71c,color:#000
    style H fill:#f9d71c,color:#000
    style I fill:#f9d71c,color:#000
    style K fill:#4caf50,color:#fff
```

## What It Looks Like

```
Episode 1  | FAIL  | reward=0.00 | skills=2   Task: "Fetch paginated users with auth"
Episode 2  | FAIL  | reward=0.00 | skills=2
Episode 3  | FAIL  | reward=0.00 | skills=2

[Evolution triggered — 3 failures on API tasks]
  → Synthesizing 'parse_json_response'... 3/3 tests passed ✓
  → Synthesizing 'fetch_all_paginated'... sandbox fail → refine → 1/1 passed ✓

Episode 4  | OK    | reward=1.00 | skills=4   Agent now has the tools it needs
```

---

## Framework Support

| Framework | Status | How |
|-----------|--------|-----|
| **Any function** | Supported | `ARISE(agent_fn=my_func)` — any `(task, tools) -> str` callable |
| **[Strands Agents](https://github.com/strands-agents/sdk-python)** | Supported | `ARISE(agent=strands_agent)` — auto-detected, tools injected alongside your `@tool` functions |
| **[LangGraph](https://github.com/langchain-ai/langgraph)** | Supported | `ARISE(agent=compiled_graph)` — auto-detected, tools converted to LangGraph format |
| **[CrewAI](https://github.com/crewAIInc/crewAI)** | Supported | `crewai_adapter(crew)` — tools injected into crew agents |
| **Raw OpenAI / Anthropic** | Supported | Wrap API calls in an `agent_fn` — see [examples/](./examples/) |

---

## Core Features

### Self-Evolution Pipeline

The core loop: **fail → detect gap → synthesize → test → promote**.

Tools are synthesized by a cheap LLM (gpt-4o-mini), validated in an isolated sandbox with adversarial testing, and version-controlled in SQLite. Every mutation is checkpointed; rollback anytime.

### Distributed Mode

Decouple agent and evolution for stateless deployments (Lambda, ECS, AgentCore):

```mermaid
flowchart LR
    subgraph Agent["Agent Process (stateless)"]
        A1["Serve requests"]
        A2["Read skills from S3"]
        A3["Report trajectories"]
    end

    subgraph Worker["ARISE Worker"]
        W1["Consume trajectories"]
        W2["Detect gaps & evolve"]
        W3["Promote skills"]
    end

    S3[(S3 Skill Store)]
    SQS[[SQS Queue]]

    A2 --> S3
    A3 --> SQS
    SQS --> W1
    W3 --> S3
```

```python
from arise import create_distributed_arise, ARISEConfig

config = ARISEConfig(
    s3_bucket="my-skills",
    sqs_queue_url="https://sqs.../arise-trajectories",
)

arise = create_distributed_arise(agent_fn=my_agent, reward_fn=task_success, config=config)
```

```bash
pip install arise-ai[aws]   # adds boto3
```

### Skill Registry

Share evolved tools across projects — like npm for agent skills:

```python
from arise.registry import SkillRegistry

registry = SkillRegistry(bucket="my-registry")
registry.publish(skill, tags=["json", "parsing"])

# Other projects can pull proven skills
skill = registry.pull("parse_csv")
```

Set `registry_check_before_synthesis=True` in config and ARISE checks the registry before calling the LLM.

### Multi-Model Routing

Route different synthesis tasks to different models:

```python
config = ARISEConfig(
    model_routes={
        "gap_detection": "gpt-4o-mini",      # cheap
        "synthesis": "claude-sonnet-4-5-20250929",  # expensive, better code
        "refinement": "gpt-4o-mini",
    },
    auto_select_model=True,  # auto-promote best model over time
)
```

### Skill A/B Testing

When ARISE evolves a refined skill, it A/B tests against the original instead of replacing it:

```python
# Automatic — ARISE creates A/B tests during evolution
# Manual — test two versions yourself
from arise.skills.ab_test import SkillABTest

ab = SkillABTest(skill_a=v1, skill_b=v2, min_episodes=20)
# Winner auto-promoted, loser deprecated after min_episodes
```

### Incremental Evolution

Patch existing skills instead of full re-synthesis:

```python
# ARISE does this automatically during evolution:
# 1. Existing skill fails on specific inputs
# 2. forge.patch() applies minimal fix
# 3. Patched version A/B tested against original
# 4. Winner promoted
```

### Reward Learning

Learn reward functions from human feedback:

```python
from arise.rewards.learned import LearnedReward

reward = LearnedReward(min_examples=10, persist_path="./feedback")
reward.add_feedback(trajectory, score=0.9)

# Falls back to task_success until enough examples collected
arise = ARISE(agent_fn=my_agent, reward_fn=reward)
```

### Cost Tracking

Track LLM spend automatically:

```python
from arise import cost_tracker

# After running episodes...
print(cost_tracker.summary())
# {"total_calls": 64, "total_input_tokens": 125000, "total_output_tokens": 42000, "total_cost_usd": 0.26}
```

---

## Benchmark Results

Evaluated on two proprietary-format domains where LLMs can't cheat with training data:

| Model | Condition | AcmeCorp (SRE) | DataCorp (Data Eng) |
|-------|-----------|---------------|-------------------|
| **Claude Sonnet** | **ARISE** | **78%** | — |
| Claude Sonnet | No tools | 63% | — |
| GPT-4o-mini | ARISE | 57% | **92%** |
| GPT-4o-mini | No tools | 48% | 50% |
| GPT-4o-mini | Fixed tools | 48% | — |

Key findings:
- **ARISE improves both models**: +15pp (Claude), +9pp (GPT-4o-mini) on AcmeCorp; +42pp on DataCorp
- **Self-evolved tools > hand-written tools**: 57% vs 48% — ARISE tailors tools to how the agent actually works
- **Fewer tools can be better**: Claude achieved 78% with just 2 tools; GPT-4o-mini needed 21

See [`benchmarks/`](./benchmarks/) for the full evaluation suite and [`paper/`](./paper/) for the research paper.

---

## Safety

Generated code is untrusted. ARISE validates through multiple layers:

| Layer | What it does |
|-------|-------------|
| **Sandbox** | Subprocess or Docker isolation with timeouts |
| **Test suite** | LLM writes tests alongside the tool |
| **Adversarial testing** | Separate LLM call tries to break it (edge cases, type boundaries, security) |
| **Import restrictions** | `allowed_imports` whitelist blocks `subprocess`, `socket`, etc. |
| **Promotion gate** | Only tools passing all tests become `ACTIVE` |
| **Version control** | SQLite checkpoints; `arise rollback <version>` anytime |
| **Rate limiting** | `max_evolutions_per_hour` caps LLM spend |

See [SECURITY.md](./SECURITY.md) for the full threat model.

---

## Reward Functions

| Function | Scores | Best for |
|----------|--------|----------|
| `task_success` | Checks `expected=`, `success=`, step errors | General purpose |
| `code_execution_reward` | 1.0 minus 0.25 per error | Tool-use agents |
| `answer_match_reward` | 1.0 exact, 0.7 substring match | Q&A, extraction |
| `efficiency_reward` | Penalizes extra steps | Concise agents |
| `llm_judge_reward` | LLM rates 0–1 (~$0.001/call) | Open-ended tasks |
| `LearnedReward` | Few-shot from human feedback | Custom domains |
| `CompositeReward` | Weighted blend of any of the above | Production |

---

### Evolution Reports + Telemetry

Track what ARISE does during evolution:

```python
arise.run(task)

# After evolution triggers:
report = arise.last_evolution
print(report.tools_promoted)    # ["compute_sha256"]
print(report.tools_rejected)    # [{"name": "fetch_api", "reason": "sandbox failure"}]
print(report.duration_ms)       # 45000
print(arise.evolution_history)  # all past reports
```

Optional OpenTelemetry integration: `pip install arise-ai[otel]` — evolution steps become OTel spans.

### Dashboard

```bash
arise dashboard ./skills              # terminal TUI (rich)
arise dashboard ./skills --web        # web UI on localhost:8501
arise dashboard ./skills --web --port 9000
```

### Distributed Setup

One command to provision AWS resources:

```bash
arise setup-distributed --region us-west-2
# Creates S3 bucket + SQS queue, saves config to .arise.json

arise setup-distributed --destroy
# Tears down resources
```

Or from Python:

```python
from arise.distributed import setup_distributed
config = setup_distributed(region="us-west-2")
# Returns ARISEConfig ready to use
```

### Skill Import/Export

```bash
arise registry export ./skills -o skills.json    # export skills as JSON
arise registry import skills.json ./skills       # import with sandbox validation
arise registry search "csv parsing" --tags json  # search registry
```

---

## CLI

```bash
# Library management
arise status ./skills          # Library stats
arise skills ./skills          # List active skills with metrics
arise inspect ./skills <id>    # View implementation + tests
arise rollback ./skills <ver>  # Rollback to previous version
arise export ./skills ./out    # Export as .py files
arise evolve --dry-run         # Preview what would be synthesized

# Dashboard
arise dashboard ./skills              # Terminal TUI
arise dashboard ./skills --web        # Web UI

# Distributed
arise setup-distributed --region us-west-2
arise setup-distributed --destroy

# Registry
arise registry export ./skills -o skills.json
arise registry import skills.json ./skills
arise registry search "csv parsing" --tags json
```

---

## Configuration

```python
from arise import ARISEConfig

config = ARISEConfig(
    model="gpt-4o-mini",           # LLM for synthesis (not your agent's model)
    sandbox_backend="subprocess",   # or "docker"
    sandbox_timeout=30,
    max_library_size=50,
    max_refinement_attempts=3,
    failure_threshold=5,            # failures before evolution
    max_evolutions_per_hour=3,      # cost control
    allowed_imports=["json", "re", "hashlib", "csv", "math"],  # restrict generated code
)
```

---

## Examples

| Example | Description |
|---------|-------------|
| [`quickstart_evolution.py`](./examples/quickstart_evolution.py) | Full evolution loop: agent fails → ARISE evolves tool → agent succeeds |
| [`quickstart.py`](./examples/quickstart.py) | Math agent evolves statistics tools |
| [`api_agent.py`](./examples/api_agent.py) | HTTP agent evolves auth + pagination (mock server) |
| [`devops_agent.py`](./examples/devops_agent.py) | DevOps agent evolves log analysis tools |
| [`coding_agent.py`](./examples/coding_agent.py) | Code agent evolves file manipulation tools |
| [`strands_agent.py`](./examples/strands_agent.py) | Strands integration with Bedrock |
| [`demo/agentcore/`](./demo/agentcore/) | AgentCore deployment with A2A protocol |

---

## Costs

Each evolution cycle is 3–5 LLM calls with gpt-4o-mini: **~$0.01–0.05 per cycle**. With `max_evolutions_per_hour=3`, worst case ~$0.15/hour.

---

## Dependencies

```bash
pip install arise-ai              # core (just pydantic)
pip install arise-ai[aws]         # + boto3 for distributed mode
pip install arise-ai[litellm]     # + litellm for multi-provider LLM
pip install arise-ai[docker]      # + docker sandbox backend
pip install arise-ai[dashboard]   # + rich, fastapi for dashboard
pip install arise-ai[otel]        # + opentelemetry for tracing
pip install arise-ai[all]         # everything
```

---

## Related Work

ARISE builds on ideas from [LATM](https://arxiv.org/abs/2305.17126) (LLMs as tool makers), [VOYAGER](https://arxiv.org/abs/2305.16291) (open-ended skill libraries), [CREATOR](https://arxiv.org/abs/2305.14318) (disentangling reasoning from tool creation), [ADAS](https://arxiv.org/abs/2408.08435) (automated agent design), and [CRAFT](https://arxiv.org/abs/2309.17428) (shared tool libraries). ARISE adds the production engineering layer: framework-agnostic integration, sandboxed validation, adversarial testing, version control, distributed deployment, and A/B testing.

## License

MIT
