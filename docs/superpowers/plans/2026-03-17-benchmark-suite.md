# ARISE Benchmark Suite Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a benchmark suite that evaluates ARISE through a realistic SRE agent onboarding scenario with proprietary formats, producing publication-ready results.

**Architecture:** AcmeCorp simulator generates deterministic test data (custom log format, metrics API, config format). Benchmark runner executes 60 episodes across 4 phases, comparing ARISE vs baselines. Plotting script generates figures for the paper.

**Tech Stack:** Python 3.11+, arise-ai, litellm, matplotlib, FastAPI (mock server), uvicorn

---

## File Structure

```
benchmarks/
├── acmecorp/
│   ├── __init__.py          # Package init, re-exports
│   ├── logs.py              # Log format generator + ground truth queries
│   ├── metrics.py           # Mock HTTP server + proprietary encoding
│   ├── config.py            # AcmeConf format generator + ground truth
│   └── fixtures.py          # Seeded environment generator
├── tasks/
│   ├── __init__.py          # Task loading helpers
│   ├── phase1_logs.py       # 15 log analysis tasks
│   ├── phase2_metrics.py    # 15 metrics API tasks
│   ├── phase3_config.py     # 15 config management tasks
│   └── phase4_incident.py   # 15 incident response tasks
├── baselines/
│   ├── __init__.py
│   └── fixed_tools.py       # Hand-written tools for fixed-toolset baseline
├── run_benchmark.py         # Main runner (CLI)
├── plot_results.py          # Generate figures + tables
├── requirements.txt         # matplotlib, fastapi, uvicorn
└── results/                 # Output directory (.gitignore'd)
    └── .gitkeep
```

---

### Task 1: AcmeCorp Log Generator

Build the custom log format generator with ground truth query functions.

**Files:**
- Create: `benchmarks/acmecorp/__init__.py`
- Create: `benchmarks/acmecorp/logs.py`
- Create: `benchmarks/tests/test_logs.py`

- [ ] **Step 1: Create package init**

Create `benchmarks/acmecorp/__init__.py`:
```python
"""AcmeCorp simulated environment for ARISE benchmarks."""
```

- [ ] **Step 2: Write failing tests for log generator**

Create `benchmarks/tests/test_logs.py`:
```python
"""Tests for AcmeCorp custom log format."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from acmecorp.logs import generate_logs, parse_log_line, query_logs

def test_generate_logs_deterministic():
    logs1 = generate_logs(seed=42, count=100)
    logs2 = generate_logs(seed=42, count=100)
    assert logs1 == logs2

def test_generate_logs_format():
    logs = generate_logs(seed=42, count=10)
    assert len(logs) == 10
    # Each line matches [ACME:SEVERITY:SERVICE:TIMESTAMP] message | ctx={...}
    for line in logs:
        assert line.startswith("[ACME:")
        assert "| ctx=" in line

def test_parse_log_line():
    line = '[ACME:ERROR:payments:1710000000] Transaction failed | ctx={"amount":450}'
    parsed = parse_log_line(line)
    assert parsed["severity"] == "ERROR"
    assert parsed["service"] == "payments"
    assert parsed["timestamp"] == 1710000000
    assert parsed["message"] == "Transaction failed"
    assert parsed["ctx"]["amount"] == 450

def test_query_count_errors():
    logs = generate_logs(seed=42, count=200)
    result = query_logs(logs, service="payments", severity="ERROR")
    assert isinstance(result, list)
    assert all(parse_log_line(l)["severity"] == "ERROR" for l in result)
    assert all(parse_log_line(l)["service"] == "payments" for l in result)

def test_query_by_time_window():
    logs = generate_logs(seed=42, count=200, start_ts=1710000000, end_ts=1710086400)
    result = query_logs(logs, start_ts=1710000000, end_ts=1710003600)
    for l in result:
        ts = parse_log_line(l)["timestamp"]
        assert 1710000000 <= ts <= 1710003600

def test_ground_truth_error_counts():
    logs = generate_logs(seed=42, count=500)
    truth = ground_truth_error_counts(logs)
    assert isinstance(truth, dict)
    # Every service in the truth dict
    for svc in ["payments", "gateway", "database", "auth", "frontend", "worker"]:
        assert svc in truth

from acmecorp.logs import ground_truth_error_counts
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd benchmarks && python -m pytest tests/test_logs.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 4: Implement log generator**

Create `benchmarks/acmecorp/logs.py`:

```python
"""AcmeCorp custom log format: [ACME:severity:service:timestamp] message | ctx={json}"""
from __future__ import annotations
import json
import random
from collections import defaultdict

SERVICES = ["payments", "gateway", "database", "auth", "frontend", "worker"]
SEVERITIES = ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]

# Weighted: mostly INFO/DEBUG, some WARN, fewer ERROR/FATAL
SEVERITY_WEIGHTS = [15, 40, 20, 20, 5]

MESSAGE_TEMPLATES = {
    "DEBUG": [
        "Config loaded for {service}",
        "Cache hit ratio: {val}%",
        "Connection pool size: {val}",
    ],
    "INFO": [
        "Request processed in {val}ms",
        "Health check OK",
        "Deployment {service}-v{val} started",
        "User login from {ip}",
    ],
    "WARN": [
        "High memory: {val}%",
        "Latency spike on /api/{endpoint}",
        "Connection pool exhaustion approaching",
        "Retry attempt {val} for upstream call",
    ],
    "ERROR": [
        "Transaction failed for user_id={val}",
        "Connection timeout to {service}",
        "Out of memory",
        "Database query timeout after {val}ms",
        "SSL certificate expires in {val} days",
    ],
    "FATAL": [
        "Service crash: segfault",
        "Disk full on /var/data",
        "Unrecoverable state corruption",
    ],
}

CTX_GENERATORS = {
    "DEBUG": lambda rng: {"cache_ratio": round(rng.uniform(80, 99), 1)},
    "INFO": lambda rng: {"latency_ms": rng.randint(5, 200), "status": 200},
    "WARN": lambda rng: {"p99_ms": rng.randint(500, 5000), "threshold_ms": 500},
    "ERROR": lambda rng: {"amount": round(rng.uniform(10, 1000), 2), "currency": rng.choice(["USD", "EUR", "GBP"]), "retry": rng.randint(0, 3)},
    "FATAL": lambda rng: {"core_dump": f"/tmp/core.{rng.randint(1000, 9999)}"},
}


def generate_logs(
    seed: int = 42,
    count: int = 500,
    start_ts: int = 1710000000,
    end_ts: int | None = None,
) -> list[str]:
    """Generate deterministic AcmeCorp log entries."""
    rng = random.Random(seed)
    if end_ts is None:
        end_ts = start_ts + 86400  # 24 hours

    lines = []
    for _ in range(count):
        severity = rng.choices(SEVERITIES, weights=SEVERITY_WEIGHTS, k=1)[0]
        service = rng.choice(SERVICES)
        timestamp = rng.randint(start_ts, end_ts)

        templates = MESSAGE_TEMPLATES[severity]
        template = rng.choice(templates)
        message = template.format(
            service=rng.choice(SERVICES),
            val=rng.randint(1, 9999),
            ip=f"{rng.randint(10,192)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}",
            endpoint=rng.choice(["users", "orders", "checkout", "health"]),
        )

        ctx = CTX_GENERATORS[severity](rng)
        line = f"[ACME:{severity}:{service}:{timestamp}] {message} | ctx={json.dumps(ctx)}"
        lines.append(line)

    lines.sort(key=lambda l: int(l.split(":")[3].split("]")[0]))
    return lines


def parse_log_line(line: str) -> dict:
    """Parse a single AcmeCorp log line into structured fields."""
    # [ACME:severity:service:timestamp] message | ctx={json}
    header, rest = line.split("] ", 1)
    parts = header[1:].split(":")  # strip leading [
    # parts = ['ACME', 'ERROR', 'payments', '1710000000']

    msg_part, ctx_part = rest.split(" | ctx=", 1)

    return {
        "severity": parts[1],
        "service": parts[2],
        "timestamp": int(parts[3]),
        "message": msg_part,
        "ctx": json.loads(ctx_part),
    }


def query_logs(
    logs: list[str],
    service: str | None = None,
    severity: str | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> list[str]:
    """Filter logs by criteria. Returns matching log lines."""
    results = []
    for line in logs:
        parsed = parse_log_line(line)
        if service and parsed["service"] != service:
            continue
        if severity and parsed["severity"] != severity:
            continue
        if start_ts and parsed["timestamp"] < start_ts:
            continue
        if end_ts and parsed["timestamp"] > end_ts:
            continue
        results.append(line)
    return results


def ground_truth_error_counts(logs: list[str]) -> dict[str, int]:
    """Compute error counts per service (ground truth for benchmarks)."""
    counts: dict[str, int] = defaultdict(int)
    for line in logs:
        parsed = parse_log_line(line)
        if parsed["severity"] in ("ERROR", "FATAL"):
            counts[parsed["service"]] += 1
    # Ensure all services present
    for svc in SERVICES:
        counts.setdefault(svc, 0)
    return dict(counts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd benchmarks && python -m pytest tests/test_logs.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add benchmarks/acmecorp/ benchmarks/tests/
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="noreply@anthropic.com" git commit --author="Claude <noreply@anthropic.com>" -m "feat(bench): add AcmeCorp log format generator with ground truth"
```

---

### Task 2: AcmeCorp Metrics Mock Server

Build the mock HTTP server with proprietary encoding.

**Files:**
- Create: `benchmarks/acmecorp/metrics.py`
- Create: `benchmarks/tests/test_metrics.py`
- Create: `benchmarks/requirements.txt`

- [ ] **Step 1: Write failing tests**

Create `benchmarks/tests/test_metrics.py` testing:
- `generate_metrics_data(seed, services)` returns deterministic data
- `encode_acme_payload(service, data)` returns `ACME_METRICS|service|ts|json` base64-encoded
- `decode_acme_payload(encoded)` round-trips correctly
- Mock server starts, responds on `/services` and `/metrics/{service}`

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement metrics server**

Create `benchmarks/acmecorp/metrics.py` with:
- `generate_metrics_data(seed, services)` — creates realistic metrics (latency p50/p95/p99, error_rate, request_count, cpu_pct, memory_pct)
- `encode_acme_payload(service, timestamp, data)` — encodes as `base64(ACME_METRICS|{service}|{ts}|{json})`
- `decode_acme_payload(encoded)` — decodes back
- `create_metrics_app(metrics_data)` — FastAPI app with `/services` and `/metrics/{service}` endpoints
- `start_metrics_server(app, port)` / `stop_metrics_server()` — thread-based server lifecycle

The `/metrics/{service}` endpoint returns:
```
Headers: X-Acme-Encoding: acme-metrics-v1, X-Acme-Service: {service}
Body: base64-encoded payload
```

Create `benchmarks/requirements.txt`:
```
matplotlib>=3.8
fastapi>=0.115.0
uvicorn>=0.34.0
httpx>=0.27.0
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add benchmarks/acmecorp/metrics.py benchmarks/tests/test_metrics.py benchmarks/requirements.txt
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="noreply@anthropic.com" git commit --author="Claude <noreply@anthropic.com>" -m "feat(bench): add AcmeCorp metrics mock server with proprietary encoding"
```

---

### Task 3: AcmeCorp Config Format

Build the AcmeConf format generator and ground truth parser.

**Files:**
- Create: `benchmarks/acmecorp/config.py`
- Create: `benchmarks/tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `benchmarks/tests/test_config.py` testing:
- `generate_configs(seed)` returns deterministic config files
- `parse_acmeconf(text)` returns structured dict
- `resolve_variables(parsed, env)` resolves `${VAR:-default}` patterns
- `diff_configs(a, b)` returns list of changes
- `validate_config(parsed, services)` checks required fields and valid dep refs
- Round-trip: generate → format → parse → equals original data

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement AcmeConf**

Create `benchmarks/acmecorp/config.py` with:
- `generate_configs(seed)` — generates 3-4 service configs + a base.acme include file
- `format_acmeconf(services_dict)` — serializes to AcmeConf string format
- `parse_acmeconf(text)` — parses AcmeConf text into `{"includes": [...], "services": {"name": {"replicas": ..., ...}}}`
- `resolve_variables(parsed, env=None)` — resolves `${VAR:-default}` using env dict or os.environ
- `diff_configs(config_a, config_b)` — returns list of `{"service": ..., "field": ..., "old": ..., "new": ...}`
- `validate_config(parsed, known_services)` — checks required fields (replicas, timeout, health_check), validates dep references exist

The format:
```
@include "base.acme"
service payments {
  replicas = ${PAYMENTS_REPLICAS:-3}
  timeout = 30s
  deps = [gateway, database]
  health_check = "/healthz"
}
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add benchmarks/acmecorp/config.py benchmarks/tests/test_config.py
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="noreply@anthropic.com" git commit --author="Claude <noreply@anthropic.com>" -m "feat(bench): add AcmeConf config format generator and parser"
```

---

### Task 4: Fixture Generator

Combines logs, metrics, and config into a single seeded environment with pre-computed ground truth.

**Files:**
- Create: `benchmarks/acmecorp/fixtures.py`
- Create: `benchmarks/tests/test_fixtures.py`

- [ ] **Step 1: Write failing tests**

Test that `generate(seed=42)` returns an `AcmeCorpEnv` with:
- `.logs` — list of 500+ log lines
- `.metrics_data` — dict of service → metrics
- `.configs` — dict of filename → AcmeConf text
- `.config_data` — parsed config data
- `.ground_truth` — dict with pre-computed answers for every benchmark task
- `.log_file_path` — path to a temp file containing all logs
- Deterministic: `generate(42) == generate(42)`

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement fixtures**

Create `benchmarks/acmecorp/fixtures.py`:
```python
@dataclass
class AcmeCorpEnv:
    logs: list[str]
    log_file_path: str
    metrics_data: dict
    metrics_port: int
    configs: dict[str, str]
    config_data: dict
    ground_truth: dict

def generate(seed: int = 42, log_count: int = 500, metrics_port: int = 18080) -> AcmeCorpEnv:
    """Generate a complete AcmeCorp environment. Same seed = same data."""
    ...
```

Ground truth dict structure:
```python
{
    "error_counts": {"payments": 42, "gateway": 31, ...},
    "errors_by_service_by_hour": {...},
    "unique_ctx_values": {...},
    "metrics": {"payments": {"p99_ms": 234, ...}, ...},
    "config_services": ["payments", "gateway", ...],
    "config_replicas": {"payments": 3, ...},
    ...
}
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add benchmarks/acmecorp/fixtures.py benchmarks/tests/test_fixtures.py
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="noreply@anthropic.com" git commit --author="Claude <noreply@anthropic.com>" -m "feat(bench): add seeded fixture generator with ground truth"
```

---

### Task 5: Phase 1-4 Task Definitions

Define all 60 tasks across 4 phases.

**Files:**
- Create: `benchmarks/tasks/__init__.py`
- Create: `benchmarks/tasks/phase1_logs.py`
- Create: `benchmarks/tasks/phase2_metrics.py`
- Create: `benchmarks/tasks/phase3_config.py`
- Create: `benchmarks/tasks/phase4_incident.py`
- Create: `benchmarks/tests/test_tasks.py`

- [ ] **Step 1: Create task structure**

Create `benchmarks/tasks/__init__.py`:
```python
from benchmarks.tasks.phase1_logs import PHASE1_TASKS
from benchmarks.tasks.phase2_metrics import PHASE2_TASKS
from benchmarks.tasks.phase3_config import PHASE3_TASKS
from benchmarks.tasks.phase4_incident import PHASE4_TASKS

ALL_TASKS = PHASE1_TASKS + PHASE2_TASKS + PHASE3_TASKS + PHASE4_TASKS

def get_tasks(quick: bool = False) -> list[dict]:
    if quick:
        return [t for t in ALL_TASKS if t["difficulty"] == "easy"]
    return ALL_TASKS
```

- [ ] **Step 2: Implement Phase 1 tasks (15 log analysis tasks)**

Each task is a function `make_tasks(env: AcmeCorpEnv) -> list[dict]` that returns tasks with `id`, `phase`, `task` (prompt string), `check` (callable), `difficulty`.

The `check(output: str, env: AcmeCorpEnv) -> bool` function validates the agent's text output against ground truth.

Example tasks:
- "How many ERROR entries for the payments service in this log file: {log_file_path}?"
- "Extract all unique user_ids from ERROR entries in {log_file_path}"
- "For each service, count errors in the last 6 hours of logs in {log_file_path}"

- [ ] **Step 3: Implement Phase 2 tasks (15 metrics API tasks)**

Tasks reference the live mock server URL. Example:
- "Fetch metrics for the payments service from http://localhost:{port}/metrics/payments and decode the response. What is the p99 latency?"
- "Which service has the highest error rate? Check all services at http://localhost:{port}"

- [ ] **Step 4: Implement Phase 3 tasks (15 config tasks)**

Tasks provide AcmeConf text inline or as file paths. Example:
- "Parse this AcmeConf config and return the replicas count for payments: {config_text}"
- "Diff these two configs and list what changed: {config_v1} vs {config_v2}"

- [ ] **Step 5: Implement Phase 4 tasks (15 incident response tasks)**

Multi-domain tasks combining logs + metrics + config. Example:
- "Service payments is showing errors. Check the logs at {log_path}, pull metrics from {url}, and check the config. What's wrong?"

- [ ] **Step 6: Write tests**

Create `benchmarks/tests/test_tasks.py`:
- All 60 tasks are generated without errors
- Each task has required fields (id, phase, task, check, difficulty)
- Check functions work with known-good outputs
- Check functions reject wrong outputs

- [ ] **Step 7: Run tests to verify they pass**

- [ ] **Step 8: Commit**

```bash
git add benchmarks/tasks/
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="noreply@anthropic.com" git commit --author="Claude <noreply@anthropic.com>" -m "feat(bench): add 60 benchmark tasks across 4 phases"
```

---

### Task 6: Fixed-Toolset Baseline

Hand-written Python tools that correctly handle all AcmeCorp formats.

**Files:**
- Create: `benchmarks/baselines/__init__.py`
- Create: `benchmarks/baselines/fixed_tools.py`
- Create: `benchmarks/tests/test_baselines.py`

- [ ] **Step 1: Implement fixed tools**

Create `benchmarks/baselines/fixed_tools.py` with these tools as standalone functions (imports inside, self-contained — same pattern ARISE-synthesized tools follow):

- `parse_acme_log(log_text: str) -> str` — parses log lines, returns JSON
- `filter_acme_logs(log_text: str, service: str = None, severity: str = None) -> str` — filters and returns matching lines
- `count_acme_errors(log_text: str) -> str` — returns error counts per service as JSON
- `fetch_acme_metrics(url: str, service: str) -> str` — HTTP GET + decode proprietary format, returns JSON
- `parse_acmeconf(config_text: str) -> str` — parses AcmeConf, returns JSON
- `validate_acmeconf(config_text: str) -> str` — validates, returns issues list
- `diff_acmeconf(config_a: str, config_b: str) -> str` — diffs two configs, returns changes

Each function takes string inputs and returns string outputs (matching how ARISE tools work with agents).

Also export `get_fixed_tools() -> list[ToolSpec]` that wraps each function as a ToolSpec.

- [ ] **Step 2: Write tests**

Test each tool against AcmeCorp fixture data. Verify correct outputs.

- [ ] **Step 3: Run tests to verify they pass**

- [ ] **Step 4: Commit**

```bash
git add benchmarks/baselines/
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="noreply@anthropic.com" git commit --author="Claude <noreply@anthropic.com>" -m "feat(bench): add fixed-toolset baseline with hand-written tools"
```

---

### Task 7: Benchmark Runner

The main CLI script that orchestrates everything.

**Files:**
- Create: `benchmarks/run_benchmark.py`
- Create: `benchmarks/results/.gitkeep`

- [ ] **Step 1: Implement runner**

Create `benchmarks/run_benchmark.py`:

```python
"""ARISE Benchmark Runner — SRE Agent Onboarding at AcmeCorp.

Usage:
    python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42
    python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --no-evolution
    python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --fixed-tools
    python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --quick
"""
```

CLI args via argparse:
- `--model` (required): LLM model name (e.g., `gpt-4o-mini`, `bedrock/claude-sonnet`)
- `--seed` (default 42): RNG seed for fixture generation
- `--mode`: `arise` (default), `no-evolution`, `fixed-tools`
- `--quick`: run only 5 tasks per phase (20 total)
- `--output-dir` (default `benchmarks/results/`)

Flow:
1. Generate `AcmeCorpEnv` from seed
2. Start metrics mock server in background thread
3. Create agent_fn (simple wrapper that calls litellm with tools)
4. Create reward_fn (wraps task check function)
5. Initialize ARISE / baseline based on mode
6. Loop episodes: run task → score → run worker inline → record
7. Write results JSON
8. Print summary table

The `agent_fn` is a simple function that:
- Builds a system prompt listing available tools
- Calls litellm with the task + tool descriptions
- If the LLM requests a tool call, executes it
- Returns the final text response

This avoids depending on Strands/external frameworks for the benchmark.

- [ ] **Step 2: Test with `--quick --mode no-evolution`**

Run: `OPENAI_API_KEY=... python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --quick --mode no-evolution`

This tests the full pipeline without spending money on evolution.

- [ ] **Step 3: Commit**

```bash
git add benchmarks/run_benchmark.py benchmarks/results/.gitkeep
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="noreply@anthropic.com" git commit --author="Claude <noreply@anthropic.com>" -m "feat(bench): add benchmark runner with CLI"
```

---

### Task 8: Plotting Script

Generate publication-ready figures from results JSON.

**Files:**
- Create: `benchmarks/plot_results.py`

- [ ] **Step 1: Implement plotter**

Create `benchmarks/plot_results.py`:

```python
"""Generate publication-ready figures from benchmark results.

Usage:
    python benchmarks/plot_results.py benchmarks/results/*.json --output figures/
"""
```

Generates 4 figures:

1. **learning_curve.pdf** — X: episode, Y: rolling success rate (window=5). Multiple lines per condition (arise, no-evolution, fixed-tools). Title: "Agent Success Rate Over Episodes."

2. **tool_accumulation.pdf** — X: episode, Y: active skill count. Annotated with tool names at jumps. Only for ARISE runs.

3. **model_comparison.pdf** — Learning curves for different models, all with ARISE.

4. **phase_breakdown.pdf** — Grouped bar chart: success rate per phase per condition.

Also generates:
- `summary_table.txt` — console-friendly table
- `summary_table.tex` — LaTeX table for the paper

Uses matplotlib with publication styling (serif fonts, appropriate figure sizes, no grid clutter).

- [ ] **Step 2: Test with sample data**

Create a small mock results JSON and verify plots generate without errors.

- [ ] **Step 3: Commit**

```bash
git add benchmarks/plot_results.py
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="noreply@anthropic.com" git commit --author="Claude <noreply@anthropic.com>" -m "feat(bench): add publication-ready plotting script"
```

---

### Task 9: Integration Test & README

Verify the full pipeline works end-to-end and document usage.

**Files:**
- Create: `benchmarks/README.md`
- Modify: `benchmarks/requirements.txt` (add any missing deps)
- Create: `benchmarks/.gitignore`

- [ ] **Step 1: Create .gitignore**

```
results/*.json
figures/
__pycache__/
*.pyc
```

- [ ] **Step 2: Write README**

Document:
- What the benchmark measures
- How to run it (all modes)
- Expected output
- How to generate figures
- Cost estimates

- [ ] **Step 3: Run full quick smoke test**

```bash
OPENAI_API_KEY=... python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --quick
```

Verify: results JSON written, no crashes, reasonable outputs.

- [ ] **Step 4: Commit**

```bash
git add benchmarks/
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="noreply@anthropic.com" git commit --author="Claude <noreply@anthropic.com>" -m "feat(bench): add README, gitignore, integration smoke test"
```

---

## Execution Order

1. **Task 1** — Log generator (foundation, no deps)
2. **Task 2** — Metrics server (independent from logs)
3. **Task 3** — Config format (independent from logs/metrics)
4. **Task 4** — Fixtures (combines 1-3)
5. **Task 5** — Task definitions (depends on 4)
6. **Task 6** — Fixed baseline (depends on 4)
7. **Task 7** — Benchmark runner (depends on 4-6)
8. **Task 8** — Plotting (depends on 7's output format)
9. **Task 9** — Integration + docs (depends on all)

Tasks 1-3 can be parallelized. Tasks 5-6 can be parallelized.
