"""Tests for benchmarks/acmecorp/metrics.py."""

import base64
import json
import time

import httpx
import pytest
import pytest_asyncio

from benchmarks.acmecorp.metrics import (
    create_metrics_app,
    decode_acme_payload,
    encode_acme_payload,
    generate_metrics_data,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SERVICES = ["api-gateway", "auth-service", "payment-service", "inventory-service"]
SEED = 42


@pytest.fixture(scope="module")
def metrics_data():
    return generate_metrics_data(SEED, SERVICES)


@pytest.fixture(scope="module")
def app(metrics_data):
    return create_metrics_app(metrics_data)


# ---------------------------------------------------------------------------
# generate_metrics_data
# ---------------------------------------------------------------------------


def test_generate_metrics_data_deterministic():
    """Same seed + services must always produce identical output."""
    data1 = generate_metrics_data(SEED, SERVICES)
    data2 = generate_metrics_data(SEED, SERVICES)
    assert data1 == data2


def test_generate_metrics_data_different_seeds_differ():
    """Different seeds should (with overwhelming probability) produce different output."""
    data1 = generate_metrics_data(1, SERVICES)
    data2 = generate_metrics_data(2, SERVICES)
    assert data1 != data2


def test_generate_metrics_data_keys(metrics_data):
    """All expected services are present."""
    assert set(metrics_data.keys()) == set(SERVICES)


def test_generate_metrics_data_field_keys(metrics_data):
    """Each service entry contains all required metric fields."""
    required = {
        "latency_p50",
        "latency_p95",
        "latency_p99",
        "error_rate",
        "request_count",
        "cpu_pct",
        "memory_pct",
    }
    for service, data in metrics_data.items():
        assert set(data.keys()) == required, f"Missing fields for {service}"


def test_generate_metrics_data_value_ranges(metrics_data):
    """Metric values fall within expected ranges."""
    for service, data in metrics_data.items():
        assert 0.0 <= data["error_rate"] <= 1.0, f"error_rate out of range for {service}"
        assert 0.0 <= data["cpu_pct"] <= 100.0, f"cpu_pct out of range for {service}"
        assert 0.0 <= data["memory_pct"] <= 100.0, f"memory_pct out of range for {service}"
        assert data["latency_p50"] > 0, f"latency_p50 must be positive for {service}"
        assert data["latency_p95"] >= data["latency_p50"], (
            f"p95 must be >= p50 for {service}"
        )
        assert data["latency_p99"] >= data["latency_p95"], (
            f"p99 must be >= p95 for {service}"
        )
        assert data["request_count"] > 0, f"request_count must be positive for {service}"


# ---------------------------------------------------------------------------
# encode_acme_payload / decode_acme_payload
# ---------------------------------------------------------------------------


def test_encode_returns_valid_base64():
    """encode_acme_payload must return a valid base64 string."""
    ts = int(time.time())
    encoded = encode_acme_payload("svc", ts, {"key": "val"})
    # Should not raise
    decoded_bytes = base64.b64decode(encoded.encode("utf-8"))
    assert decoded_bytes  # non-empty


def test_payload_format_prefix():
    """The decoded payload must start with ACME_METRICS|."""
    ts = 1700000000
    encoded = encode_acme_payload("svc", ts, {"x": 1})
    raw = base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
    assert raw.startswith("ACME_METRICS|")


def test_payload_format_structure():
    """Payload must have exactly 4 pipe-separated sections."""
    ts = 1700000000
    data = {"latency_p50": 12.3}
    encoded = encode_acme_payload("my-service", ts, data)
    raw = base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
    parts = raw.split("|", 3)
    assert len(parts) == 4
    assert parts[0] == "ACME_METRICS"
    assert parts[1] == "my-service"
    assert parts[2] == str(ts)
    assert json.loads(parts[3]) == data


def test_encode_decode_roundtrip():
    """decode_acme_payload must invert encode_acme_payload exactly."""
    ts = 1700000000
    service = "checkout-service"
    data = {"latency_p50": 25.0, "error_rate": 0.01}
    encoded = encode_acme_payload(service, ts, data)
    decoded = decode_acme_payload(encoded)
    assert decoded["service"] == service
    assert decoded["timestamp"] == ts
    assert decoded["data"] == data


def test_decode_invalid_payload_raises():
    """decode_acme_payload must raise ValueError for a malformed payload."""
    garbage = base64.b64encode(b"NOT_VALID|x|y|z").decode("utf-8")
    with pytest.raises(ValueError):
        decode_acme_payload(garbage)


# ---------------------------------------------------------------------------
# FastAPI application — /services
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_services_returns_all(app, metrics_data):
    """GET /services must return all service names."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/services")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert set(body) == set(metrics_data.keys())


@pytest.mark.asyncio
async def test_list_services_content_type(app):
    """GET /services must return application/json."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/services")
    assert "application/json" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# FastAPI application — /metrics/{service}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_metrics_status_200(app):
    """GET /metrics/<known-service> must return 200."""
    service = SERVICES[0]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/metrics/{service}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_metrics_unknown_service_404(app):
    """GET /metrics/<unknown-service> must return 404."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/metrics/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_metrics_header_encoding(app):
    """Response must include X-Acme-Encoding: acme-metrics-v1."""
    service = SERVICES[0]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/metrics/{service}")
    assert response.headers.get("x-acme-encoding") == "acme-metrics-v1"


@pytest.mark.asyncio
async def test_get_metrics_header_service(app):
    """Response must include X-Acme-Service matching the requested service."""
    service = SERVICES[1]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/metrics/{service}")
    assert response.headers.get("x-acme-service") == service


@pytest.mark.asyncio
async def test_get_metrics_body_is_valid_base64(app):
    """Response body must be a valid base64 string."""
    service = SERVICES[0]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/metrics/{service}")
    body = response.text.strip()
    # Must not raise
    decoded = base64.b64decode(body.encode("utf-8"))
    assert decoded


@pytest.mark.asyncio
async def test_get_metrics_body_decodes_correctly(app, metrics_data):
    """Decoded payload data must match the original metrics_data for the service."""
    service = SERVICES[2]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/metrics/{service}")
    body = response.text.strip()
    decoded = decode_acme_payload(body)
    assert decoded["service"] == service
    assert decoded["data"] == metrics_data[service]


@pytest.mark.asyncio
async def test_get_metrics_with_window_param(app):
    """GET /metrics/{service}?window=1h must still return 200."""
    service = SERVICES[0]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/metrics/{service}", params={"window": "1h"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_metrics_payload_starts_with_acme(app):
    """The raw (decoded-from-base64) payload must start with ACME_METRICS|."""
    service = SERVICES[3]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/metrics/{service}")
    body = response.text.strip()
    raw = base64.b64decode(body.encode("utf-8")).decode("utf-8")
    assert raw.startswith("ACME_METRICS|")
