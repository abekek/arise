"""AcmeCorp custom log format generator with ground truth query functions.

Log format: [ACME:severity:service:unix_timestamp] message | ctx={json}
"""

import json
import random
import re
from collections import defaultdict
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────

SEVERITIES = ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]

# Weighted distribution: mostly INFO/DEBUG, fewer ERROR/FATAL
SEVERITY_WEIGHTS = {
    "DEBUG": 30,
    "INFO":  45,
    "WARN":  14,
    "ERROR":  9,
    "FATAL":  2,
}

SERVICES = ["payments", "gateway", "database", "auth", "frontend", "worker"]

# ── Message templates per severity ───────────────────────────────────────────

_MESSAGES = {
    "DEBUG": [
        "entering handler",
        "cache lookup for key={key}",
        "SQL query prepared: SELECT * FROM {table} WHERE id=?",
        "connection pool size={pool_size}",
        "config reloaded from {config_source}",
        "retry attempt {retry} of {max_retry}",
        "span started trace_id={trace_id}",
        "serializing payload size={size}B",
    ],
    "INFO": [
        "request processed successfully",
        "user {user_id} authenticated",
        "payment of {amount} {currency} completed",
        "job {job_id} dispatched",
        "service started on port {port}",
        "health check passed",
        "session {session_id} created",
        "record {record_id} updated",
        "webhook delivered to {endpoint}",
        "rate limit: {remaining} requests remaining",
    ],
    "WARN": [
        "slow query detected: {duration_ms}ms",
        "cache miss ratio high: {miss_ratio:.2f}",
        "retrying failed request attempt={retry}",
        "disk usage at {disk_pct}%",
        "deprecated API endpoint called",
        "token expiring in {seconds}s",
        "queue depth elevated: {depth} items",
        "response time degraded: {duration_ms}ms",
    ],
    "ERROR": [
        "request failed: {error}",
        "database connection refused",
        "payment declined for user {user_id}: {reason}",
        "timeout after {duration_ms}ms waiting for {service}",
        "authentication failed for user {user_id}",
        "unhandled exception in {handler}: {error}",
        "circuit breaker OPEN for {service}",
        "failed to publish message to queue: {error}",
    ],
    "FATAL": [
        "out of memory: process terminating",
        "data corruption detected in {table}",
        "unrecoverable error: {error}",
        "disk full — writes halted",
        "SSL certificate invalid: {error}",
    ],
}

# ── Context field generators per severity ────────────────────────────────────

def _make_ctx(rng: random.Random, severity: str, service: str) -> dict:
    """Return a realistic ctx dict for the given severity and service."""
    base: dict[str, Any] = {
        "host": rng.choice(["web-01", "web-02", "worker-01", "worker-02", "db-primary"]),
        "region": rng.choice(["us-east-1", "us-west-2", "eu-west-1"]),
    }

    if severity == "DEBUG":
        base["trace_id"] = _hex(rng, 16)
        base["span_id"] = _hex(rng, 8)
        base["pid"] = rng.randint(1000, 65535)

    elif severity == "INFO":
        base["request_id"] = _hex(rng, 12)
        base["duration_ms"] = rng.randint(5, 300)
        if service == "payments":
            base["transaction_id"] = f"txn_{_hex(rng, 10)}"
            base["amount"] = round(rng.uniform(1.0, 9999.99), 2)
            base["currency"] = rng.choice(["USD", "EUR", "GBP"])
        elif service == "auth":
            base["user_id"] = f"usr_{rng.randint(1000, 99999)}"
            base["method"] = rng.choice(["password", "oauth", "apikey", "mfa"])
        elif service == "database":
            base["query_type"] = rng.choice(["SELECT", "INSERT", "UPDATE", "DELETE"])
            base["rows_affected"] = rng.randint(0, 5000)

    elif severity == "WARN":
        base["duration_ms"] = rng.randint(500, 5000)
        base["threshold_ms"] = rng.choice([500, 1000, 2000])
        base["retry"] = rng.randint(1, 3)
        base["request_id"] = _hex(rng, 12)

    elif severity == "ERROR":
        base["error_code"] = rng.choice(["E1001", "E1002", "E2001", "E3001", "E5000"])
        base["request_id"] = _hex(rng, 12)
        base["duration_ms"] = rng.randint(100, 30000)
        base["stack_depth"] = rng.randint(3, 20)
        if service == "payments":
            base["transaction_id"] = f"txn_{_hex(rng, 10)}"

    elif severity == "FATAL":
        base["error_code"] = rng.choice(["F0001", "F0002", "F0003"])
        base["memory_mb"] = rng.randint(512, 8192)
        base["uptime_s"] = rng.randint(60, 86400)

    return base


def _hex(rng: random.Random, length: int) -> str:
    return "".join(rng.choices("0123456789abcdef", k=length))


# ── Template rendering ───────────────────────────────────────────────────────

def _render_message(rng: random.Random, severity: str, service: str) -> str:
    template = rng.choice(_MESSAGES[severity])
    # Fill any {placeholder} tokens with plausible values
    replacements = {
        "key": _hex(rng, 8),
        "table": rng.choice(["users", "orders", "payments", "sessions", "events"]),
        "pool_size": rng.randint(5, 50),
        "config_source": rng.choice(["s3", "consul", "env", "file"]),
        "retry": rng.randint(1, 5),
        "max_retry": 5,
        "trace_id": _hex(rng, 16),
        "size": rng.randint(64, 65536),
        "user_id": f"usr_{rng.randint(1000, 99999)}",
        "amount": round(rng.uniform(1.0, 9999.99), 2),
        "currency": rng.choice(["USD", "EUR", "GBP"]),
        "job_id": f"job_{_hex(rng, 8)}",
        "port": rng.choice([3000, 8080, 8443, 9000]),
        "session_id": f"sess_{_hex(rng, 12)}",
        "record_id": rng.randint(1, 999999),
        "endpoint": rng.choice(["https://hooks.example.com/a", "https://api.partner.io/cb"]),
        "remaining": rng.randint(0, 1000),
        "duration_ms": rng.randint(1, 30000),
        "miss_ratio": rng.uniform(0.05, 0.95),
        "disk_pct": rng.randint(70, 99),
        "seconds": rng.randint(30, 3600),
        "depth": rng.randint(100, 10000),
        "error": rng.choice(["connection reset", "timeout", "permission denied", "not found"]),
        "reason": rng.choice(["insufficient funds", "card expired", "fraud detected"]),
        "service": rng.choice(SERVICES),
        "handler": rng.choice(["RequestHandler", "PaymentProcessor", "AuthMiddleware"]),
    }
    try:
        return template.format(**replacements)
    except KeyError:
        return template


# ── Public API ───────────────────────────────────────────────────────────────

_LOG_RE = re.compile(
    r"^\[ACME:(?P<severity>[A-Z]+):(?P<service>[a-z]+):(?P<timestamp>\d+)\] "
    r"(?P<message>.+?) \| ctx=(?P<ctx>\{.*\})$"
)


def generate_logs(
    seed: int,
    count: int = 500,
    start_ts: int = 1710000000,
    end_ts: int | None = None,
) -> list[str]:
    """Generate ``count`` log lines deterministically from ``seed``.

    Returns lines sorted by ascending timestamp.
    """
    if end_ts is None:
        end_ts = start_ts + 86400  # default: one day window

    rng = random.Random(seed)

    sev_population = [s for s, w in SEVERITY_WEIGHTS.items() for _ in range(w)]

    entries: list[tuple[int, str]] = []
    for _ in range(count):
        ts = rng.randint(start_ts, end_ts)
        severity = rng.choice(sev_population)
        service = rng.choice(SERVICES)
        message = _render_message(rng, severity, service)
        ctx = _make_ctx(rng, severity, service)
        ctx_str = json.dumps(ctx, separators=(",", ":"))
        line = f"[ACME:{severity}:{service}:{ts}] {message} | ctx={ctx_str}"
        entries.append((ts, line))

    entries.sort(key=lambda x: x[0])
    return [line for _, line in entries]


def parse_log_line(line: str) -> dict:
    """Parse a single log line into a dict.

    Keys: severity, service, timestamp (int), message, ctx (dict).
    Raises ValueError if the line does not match the expected format.
    """
    m = _LOG_RE.match(line)
    if not m:
        raise ValueError(f"Cannot parse log line: {line!r}")
    return {
        "severity": m.group("severity"),
        "service": m.group("service"),
        "timestamp": int(m.group("timestamp")),
        "message": m.group("message"),
        "ctx": json.loads(m.group("ctx")),
    }


def query_logs(
    logs: list[str],
    service: str | None = None,
    severity: str | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> list[str]:
    """Filter log lines by optional service, severity, and/or time window.

    All supplied filters are ANDed together.
    """
    results = []
    for line in logs:
        parsed = parse_log_line(line)
        if service is not None and parsed["service"] != service:
            continue
        if severity is not None and parsed["severity"] != severity:
            continue
        if start_ts is not None and parsed["timestamp"] < start_ts:
            continue
        if end_ts is not None and parsed["timestamp"] > end_ts:
            continue
        results.append(line)
    return results


def ground_truth_error_counts(logs: list[str]) -> dict[str, int]:
    """Return mapping of service → count of ERROR + FATAL lines."""
    counts: dict[str, int] = defaultdict(int)
    for line in logs:
        parsed = parse_log_line(line)
        if parsed["severity"] in ("ERROR", "FATAL"):
            counts[parsed["service"]] += 1
    return dict(counts)


def ground_truth_ctx_values(logs: list[str], field: str) -> list:
    """Return sorted list of unique values for ``field`` across all ctx dicts."""
    seen = set()
    for line in logs:
        parsed = parse_log_line(line)
        if field in parsed["ctx"]:
            val = parsed["ctx"][field]
            # Make unhashable values hashable for deduplication
            if isinstance(val, (list, dict)):
                val = json.dumps(val, sort_keys=True)
            seen.add(val)
    return sorted(seen, key=str)


def ground_truth_errors_by_hour(logs: list[str]) -> dict[int, int]:
    """Return mapping of hour (unix timestamp of hour start) → error count.

    Only ERROR and FATAL entries are counted.
    """
    counts: dict[int, int] = defaultdict(int)
    for line in logs:
        parsed = parse_log_line(line)
        if parsed["severity"] in ("ERROR", "FATAL"):
            hour = (parsed["timestamp"] // 3600) * 3600
            counts[hour] += 1
    return dict(counts)
