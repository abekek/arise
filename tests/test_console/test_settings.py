import pytest
from fastapi.testclient import TestClient
from arise.console.server import create_console_app


@pytest.fixture
def client(tmp_path):
    app = create_console_app(data_dir=str(tmp_path))
    return TestClient(app)


def test_get_settings_defaults(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_model"] == "gpt-4o-mini"
    assert data["default_sandbox"] == "subprocess"
    assert data["default_failure_threshold"] == 5
    assert data["openai_key_set"] is False
    assert data["anthropic_key_set"] is False
    assert data["aws_region"] == "us-east-1"


def test_update_settings(client):
    resp = client.put("/api/settings", json={
        "default_model": "claude-sonnet-4-20250514",
        "default_sandbox": "docker",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_model"] == "claude-sonnet-4-20250514"
    assert data["default_sandbox"] == "docker"

    # Verify persistence
    resp = client.get("/api/settings")
    data = resp.json()
    assert data["default_model"] == "claude-sonnet-4-20250514"
    assert data["default_sandbox"] == "docker"


def test_update_settings_partial(client):
    client.put("/api/settings", json={"default_model": "gpt-4o"})
    resp = client.put("/api/settings", json={"default_failure_threshold": 10})
    data = resp.json()
    assert data["default_model"] == "gpt-4o"
    assert data["default_failure_threshold"] == 10
