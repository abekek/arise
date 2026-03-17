# ARISE Benchmark Suite — SRE Agent Onboarding

Evaluates ARISE through a realistic scenario: an SRE agent onboarding at "AcmeCorp" — a company with proprietary log formats, metrics APIs, and config files that don't exist in LLM training data.

## The Scenario

AcmeCorp uses three custom systems:

| System | Format | Why LLM can't cheat |
|--------|--------|---------------------|
| **Logs** | `[ACME:severity:service:ts] msg \| ctx={json}` | Custom format, must be parsed |
| **Metrics API** | Base64-encoded `ACME_METRICS\|svc\|ts\|json` | Must decode proprietary encoding |
| **Config (AcmeConf)** | Custom syntax with `${VAR:-default}`, duration literals | Not YAML/JSON/TOML |

## 60 Tasks, 4 Phases

| Phase | Domain | Episodes | What the agent needs |
|-------|--------|----------|---------------------|
| 1 | Log Analysis | 1-15 | Parse custom format, filter, aggregate |
| 2 | Metrics API | 16-30 | HTTP calls + decode proprietary response |
| 3 | Config Management | 31-45 | Parse AcmeConf, validate, diff |
| 4 | Incident Response | 46-60 | Compose tools from all phases |

## Running

```bash
pip install -r benchmarks/requirements.txt

# Full benchmark with ARISE (real LLM calls, ~$1 for gpt-4o-mini)
OPENAI_API_KEY=... python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42

# No-tools baseline (agent with raw LLM reasoning only)
python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --no-evolution

# Fixed-toolset baseline (hand-written tools, no evolution)
python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --fixed-tools

# Quick smoke test (20 tasks)
python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --quick
```

## Generating Figures

```bash
python benchmarks/plot_results.py benchmarks/results/*.json --output benchmarks/figures/
```

Produces:
- `learning_curve.pdf` — success rate over episodes (ARISE vs baselines)
- `tool_accumulation.pdf` — skill library growth
- `model_comparison.pdf` — different models with ARISE
- `phase_breakdown.pdf` — success rate per domain
- `summary_table.txt` / `summary_table.tex` — for the paper

## 3 Conditions

| Condition | What it tests |
|-----------|--------------|
| **arise** | Full self-evolution: agent starts with 0 tools, evolves them from failures |
| **no-evolution** | Raw LLM reasoning, no tools at all |
| **fixed-tools** | Hand-written tools from day 1 (the ceiling ARISE aims to approach) |

## Cost

~$1 per full run (gpt-4o-mini), ~$6 per run (Claude Sonnet). Full benchmark suite (2 models x 3 conditions): ~$20-25.
