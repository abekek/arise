# ARISE Benchmark Suite — SRE Agent Onboarding

## Goal

Evaluate ARISE's self-evolution capability through a realistic scenario: an SRE agent onboarding to "AcmeCorp," a company with proprietary systems no LLM has seen before. The agent starts with zero tools and must evolve them to operate the company's custom infrastructure.

The benchmark produces publication-ready results: learning curves, tool accumulation plots, baseline comparisons, model comparisons, and cost analysis.

## Why This Scenario

AcmeCorp uses custom formats for logs, metrics, and configs. These formats don't exist in LLM training data, so the agent can't cheat with raw reasoning. It must synthesize tools that parse, decode, and manipulate these formats — proving ARISE enables genuine capability acquisition.

## Architecture

```
benchmarks/
├── acmecorp/                # Simulated company environment
│   ├── __init__.py
│   ├── logs.py              # Custom log format generator + ground truth
│   ├── metrics.py           # Mock metrics HTTP server + proprietary encoding
│   ├── config.py            # AcmeConf format generator + parser ground truth
│   └── fixtures.py          # Seeded fixture generator (deterministic)
├── tasks/                   # Task definitions per phase
│   ├── __init__.py
│   ├── phase1_logs.py       # 15 log analysis tasks
│   ├── phase2_metrics.py    # 15 metrics API tasks
│   ├── phase3_config.py     # 15 config management tasks
│   └── phase4_incident.py   # 15 incident response tasks
├── baselines/
│   ├── __init__.py
│   └── fixed_tools.py       # Hand-written tools for the fixed-toolset baseline
├── run_benchmark.py         # Main benchmark runner
├── plot_results.py          # Generate publication-ready figures
└── results/                 # Output directory for JSON results
```

## AcmeCorp Environment

### Custom Log Format

```
[ACME:ERROR:payments:1710000000] Transaction failed for user_id=8831 | ctx={"amount":450.00,"currency":"USD","retry":2}
[ACME:WARN:gateway:1710000001] Latency spike on /api/checkout | ctx={"p99_ms":2300,"threshold_ms":500}
```

Fields: `[ACME:severity:service:unix_timestamp] message | ctx=json_object`

Severities: DEBUG, INFO, WARN, ERROR, FATAL. Services: payments, gateway, database, auth, frontend, worker.

`logs.py` generates realistic log data with configurable parameters (number of entries, error rate, services, time range). Ground truth functions compute correct answers for any query.

### Metrics API (Mock HTTP Server)

Endpoints:
- `GET /services` — returns list of service names
- `GET /metrics/{service}?window={duration}` — returns base64-encoded payload with custom header

Response format:
```
X-Acme-Encoding: acme-metrics-v1
X-Acme-Service: payments

<base64 payload>
```

Decoded payload is a custom binary-ish format: `ACME_METRICS|{service}|{timestamp}|{json_data}`. The agent must learn to decode this — calling the API alone isn't enough.

`metrics.py` implements the Flask/FastAPI mock server and generates realistic metrics (latency p50/p95/p99, error rate, request count, CPU/memory).

### AcmeConf Config Format

```
@include "base.acme"
service payments {
  replicas = ${PAYMENTS_REPLICAS:-3}
  timeout = 30s
  deps = [gateway, database]
  health_check = "/healthz"
}
```

Features: `@include` directives, `service` blocks with `key = value` pairs, variable interpolation `${VAR:-default}`, duration literals (`30s`, `5m`), list values (`[a, b, c]`).

`config.py` generates valid AcmeConf files and provides ground truth parsing/validation/diffing.

### Fixture Generator

`fixtures.py` provides `generate(seed: int)` which creates a complete AcmeCorp environment:
- 500+ log entries across 6 services over a 24-hour window
- Metrics data for all services with realistic patterns (including anomalies)
- 3-4 config files with variable references and includes
- Pre-computed ground truth answers for every task

Same seed = identical environment = reproducible benchmark runs.

## Task Design

60 tasks across 4 phases. Each task is a dict:

```python
{
    "id": "log-01",
    "phase": 1,
    "task": "How many ERROR entries are there for the payments service?",
    "check": lambda output, truth: str(truth["payments_errors"]) in output,
    "difficulty": "easy",
}
```

The `check` function validates the agent's output against pre-computed ground truth. No LLM judging — purely deterministic scoring.

### Phase 1: Log Analysis (episodes 1-15)

Easy (1-3): Count errors for a single service.
Medium (4-9): Extract ctx fields, filter by thresholds.
Hard (10-15): Cross-service correlation, time-windowed aggregation, summary reports.

Tools the agent needs to evolve: `parse_acme_log`, `filter_log_entries`, `aggregate_log_stats`.

### Phase 2: Metrics API (episodes 16-30)

Easy (16-18): Fetch and decode metrics for one service.
Medium (19-24): Compare services, detect SLO violations.
Hard (25-30): Multi-service dashboards, anomaly detection over time windows.

Tools needed: `fetch_acme_metrics`, `decode_acme_payload`, `compute_slo_status`.

### Phase 3: Config Management (episodes 31-45)

Easy (31-33): Parse AcmeConf, extract service config.
Medium (34-39): Validate configs, diff two versions.
Hard (40-45): Resolve variables, apply patches, serialize back.

Tools needed: `parse_acmeconf`, `validate_acmeconf`, `diff_acmeconf`.

### Phase 4: Incident Response (episodes 46-60)

Multi-step tasks composing tools from all previous phases:
- Easy (46-48): Single-domain incident ("check logs for service X").
- Medium (49-54): Two-domain incident ("check logs AND metrics").
- Hard (55-60): Full incident response combining all three domains plus reasoning.

No new tools needed — tests whether the evolved library composes correctly.

## Benchmark Runner

`run_benchmark.py` orchestrates the full evaluation.

### Modes

```bash
# Full benchmark with ARISE
python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42

# Claude Sonnet
python benchmarks/run_benchmark.py --model bedrock/claude-sonnet --seed 42

# No-tools baseline (ARISE disabled)
python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --no-evolution

# Fixed-toolset baseline (hand-written tools)
python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --fixed-tools

# Quick smoke test (5 episodes per phase = 20 total)
python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --quick
```

### Execution Flow

1. Generate fixtures with seed
2. Start mock metrics HTTP server
3. Initialize ARISE (or baseline) with zero skills
4. For each episode (1-60):
   a. Select task from current phase
   b. Run `arise.run(task)` (or baseline agent)
   c. Score output with deterministic `check` function
   d. Run `worker.run_once()` inline to process any trajectories
   e. Record result
5. Stop server, write results JSON

The worker runs inline (not background) for reproducibility.

### Results Format

`results/{model}_{mode}_{seed}_{timestamp}.json`:

```json
{
    "model": "gpt-4o-mini",
    "mode": "arise",
    "seed": 42,
    "episodes": [
        {
            "episode": 1,
            "phase": 1,
            "task_id": "log-01",
            "task": "How many ERROR entries...",
            "success": false,
            "reward": 0.0,
            "skills_count": 0,
            "tools_used": [],
            "latency_ms": 2340,
            "synthesis_cost_usd": 0.0
        }
    ],
    "summary": {
        "total_success_rate": 0.72,
        "phase_success_rates": [0.53, 0.67, 0.80, 0.87],
        "total_tools_evolved": 8,
        "total_cost_usd": 0.34,
        "total_latency_s": 245
    }
}
```

## Baselines

### No-tools baseline

ARISE disabled. The agent receives tasks with no tools and must answer with raw LLM reasoning. Expected to fail on most tasks since the formats are proprietary.

### Fixed-toolset baseline

Hand-written Python tools in `baselines/fixed_tools.py` that correctly parse all AcmeCorp formats. Represents "an engineer spent an afternoon building tools." The agent starts with all tools from episode 1. This is the ceiling ARISE aims to approach.

Tools provided: `parse_acme_log`, `filter_logs`, `fetch_acme_metrics`, `decode_acme_payload`, `parse_acmeconf`, `validate_acmeconf`, `diff_acmeconf`.

## Measurements

### Primary Plots

1. **Learning curve** — X: episode, Y: rolling success rate (window=5). Three lines: ARISE, fixed-tools, no-tools. Shows agent improving over time.

2. **Tool accumulation** — X: episode, Y: active skill count. Annotated with tool names at each jump.

3. **Model comparison** — Learning curve with gpt-4o-mini vs Claude Sonnet, both using ARISE.

4. **Phase breakdown** — Grouped bar chart: success rate per phase per condition.

### Tables

| Metric | Description |
|--------|-------------|
| Final success rate | Main result per condition |
| Synthesis success rate | % tools passing sandbox on first try |
| Avg refinement attempts | Mean refine cycles per tool |
| Total tools evolved | Library size at end |
| Total cost (USD) | LLM spend for synthesis |
| Avg episode latency | ARISE overhead vs raw agent |

### Ablations (stretch)

- Without adversarial testing
- Without incremental patching (full re-synthesis only)
- Different synthesis models (gpt-4o-mini vs gpt-4o)

## Plotting

`plot_results.py` reads result JSON files and generates:
- matplotlib figures saved as PDF (publication-ready)
- Console summary table
- LaTeX table snippets for the paper

```bash
python benchmarks/plot_results.py results/*.json --output figures/
```

## Cost Estimate

Per full run (60 episodes, one model):
- Agent LLM calls: ~60 calls, ~$0.50 (gpt-4o-mini) or ~$5 (Claude Sonnet)
- Synthesis LLM calls: ~15-25 calls, ~$0.15-0.30
- Total per run: ~$1 (gpt-4o-mini) or ~$6 (Claude Sonnet)

Full benchmark (2 models x 3 conditions): ~$20-25 total.
