"""AcmeCorp mock metrics HTTP server with proprietary encoding."""

import base64
import json
import random
import threading
import time
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response


# ---------------------------------------------------------------------------
# Encoding / decoding
# ---------------------------------------------------------------------------

def encode_acme_payload(service: str, timestamp: int, data: dict) -> str:
    """Encode metrics into the ACME proprietary base64 payload.

    Format: Base64( ACME_METRICS|{service}|{unix_timestamp}|{json_data} )
    """
    json_data = json.dumps(data, separators=(",", ":"))
    raw = f"ACME_METRICS|{service}|{timestamp}|{json_data}"
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_acme_payload(encoded: str) -> dict:
    """Decode an ACME base64 payload.

    Returns a dict with keys: service, timestamp, data.
    """
    raw = base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
    # Split on the first three pipes only — json_data may contain pipes
    parts = raw.split("|", 3)
    if len(parts) != 4 or parts[0] != "ACME_METRICS":
        raise ValueError(f"Invalid ACME payload: {raw!r}")
    _, service, ts_str, json_data = parts
    return {
        "service": service,
        "timestamp": int(ts_str),
        "data": json.loads(json_data),
    }


# ---------------------------------------------------------------------------
# Metrics generation
# ---------------------------------------------------------------------------

_METRIC_KEYS = [
    "latency_p50",
    "latency_p95",
    "latency_p99",
    "error_rate",
    "request_count",
    "cpu_pct",
    "memory_pct",
]


def generate_metrics_data(seed: int, services: list[str]) -> dict[str, dict[str, Any]]:
    """Generate deterministic metrics for each service.

    Args:
        seed: Random seed for reproducibility.
        services: List of service names.

    Returns:
        A dict mapping service name → metrics dict with keys:
        latency_p50, latency_p95, latency_p99, error_rate,
        request_count, cpu_pct, memory_pct.
    """
    rng = random.Random(seed)
    result: dict[str, dict[str, Any]] = {}

    for service in services:
        p50 = round(rng.uniform(5.0, 200.0), 3)
        p95 = round(p50 * rng.uniform(1.5, 4.0), 3)
        p99 = round(p95 * rng.uniform(1.1, 2.5), 3)
        error_rate = round(rng.uniform(0.0, 1.0), 6)
        request_count = rng.randint(100, 1_000_000)
        cpu_pct = round(rng.uniform(0.0, 100.0), 2)
        memory_pct = round(rng.uniform(0.0, 100.0), 2)

        result[service] = {
            "latency_p50": p50,
            "latency_p95": p95,
            "latency_p99": p99,
            "error_rate": error_rate,
            "request_count": request_count,
            "cpu_pct": cpu_pct,
            "memory_pct": memory_pct,
        }

    return result


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

def create_metrics_app(metrics_data: dict[str, dict[str, Any]]) -> FastAPI:
    """Create a FastAPI app exposing the AcmeCorp metrics API.

    Args:
        metrics_data: Mapping of service name → metrics dict (from generate_metrics_data).

    Returns:
        A configured FastAPI application.
    """
    app = FastAPI(title="AcmeCorp Metrics API")

    @app.get("/services")
    def list_services() -> list[str]:
        """Return a JSON list of all known service names."""
        return list(metrics_data.keys())

    @app.get("/metrics/{service}")
    def get_metrics(service: str, window: str = "5m") -> Response:
        """Return encoded metrics for a given service.

        Query param:
            window: duration string (e.g. "5m", "1h") — accepted but not used
                    in mock; included for API compatibility.

        Response headers:
            X-Acme-Encoding: acme-metrics-v1
            X-Acme-Service: {service}

        Body: base64-encoded ACME payload.
        """
        if service not in metrics_data:
            raise HTTPException(status_code=404, detail=f"Service '{service}' not found")

        timestamp = int(time.time())
        payload = encode_acme_payload(service, timestamp, metrics_data[service])

        return Response(
            content=payload,
            media_type="text/plain",
            headers={
                "X-Acme-Encoding": "acme-metrics-v1",
                "X-Acme-Service": service,
            },
        )

    return app


# ---------------------------------------------------------------------------
# Server lifecycle helpers
# ---------------------------------------------------------------------------

class _UvicornServer(uvicorn.Server):
    """Uvicorn server that can be stopped programmatically."""

    def install_signal_handlers(self) -> None:  # type: ignore[override]
        # Prevent uvicorn from overriding the process signal handlers.
        pass


def start_metrics_server(app: FastAPI, port: int = 18080) -> threading.Thread:
    """Start the metrics server in a daemon thread.

    Args:
        app: The FastAPI application to serve.
        port: TCP port to listen on (default 18080).

    Returns:
        The daemon thread running the server.
    """
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = _UvicornServer(config=config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait briefly until the server is ready
    deadline = time.time() + 5.0
    while not server.started and time.time() < deadline:
        time.sleep(0.05)

    # Attach the server instance to the thread so stop_metrics_server can reach it
    thread._acme_server = server  # type: ignore[attr-defined]
    return thread


def stop_metrics_server(thread: threading.Thread) -> None:
    """Signal the metrics server to shut down and wait for the thread to finish.

    Args:
        thread: The thread returned by start_metrics_server.
    """
    server: _UvicornServer = getattr(thread, "_acme_server", None)
    if server is not None:
        server.should_exit = True
    thread.join(timeout=5.0)
