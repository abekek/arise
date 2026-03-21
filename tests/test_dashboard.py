import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise.types import Skill, SkillStatus, SkillOrigin, Trajectory, Step
from arise.skills.library import SkillLibrary
from arise.trajectory.store import TrajectoryStore


def _setup():
    skills_path = tempfile.mkdtemp()
    traj_path = tempfile.mkdtemp()
    lib = SkillLibrary(skills_path)
    store = TrajectoryStore(traj_path)

    skill = Skill(
        name="test_skill",
        description="A test skill",
        implementation="def test_skill(x): return x",
        origin=SkillOrigin.MANUAL,
        status=SkillStatus.ACTIVE,
        invocation_count=10,
        success_count=8,
    )
    lib.add(skill)
    lib.checkpoint("Initial")

    traj = Trajectory(
        task="Solve a math problem",
        steps=[Step(observation="start", reasoning="think", action="compute", result="42")],
        outcome="success",
        reward=0.95,
    )
    store.save(traj)

    return skills_path, traj_path, lib, store


# --- TUI tests ---

def test_tui_runs_without_error():
    skills_path, traj_path, _, _ = _setup()
    try:
        from arise.dashboard.tui import run_tui
        # run_tui prints to console; just verify no exceptions
        run_tui(skills_path, traj_path)
    finally:
        shutil.rmtree(skills_path)
        shutil.rmtree(traj_path)


def test_tui_empty():
    skills_path = tempfile.mkdtemp()
    traj_path = tempfile.mkdtemp()
    try:
        from arise.dashboard.tui import run_tui
        run_tui(skills_path, traj_path)
    finally:
        shutil.rmtree(skills_path)
        shutil.rmtree(traj_path)


# --- Web API tests ---

def test_web_api_skills():
    skills_path, traj_path, _, _ = _setup()
    try:
        from fastapi.testclient import TestClient
        from arise.dashboard.web import create_app

        app = create_app(skills_path, traj_path)
        client = TestClient(app)

        resp = client.get("/api/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test_skill"
        assert data[0]["status"] == "active"
        assert data[0]["invocations"] == 10
        assert data[0]["success_rate"] == 0.8
    finally:
        shutil.rmtree(skills_path)
        shutil.rmtree(traj_path)


def test_web_api_trajectories():
    skills_path, traj_path, _, _ = _setup()
    try:
        from fastapi.testclient import TestClient
        from arise.dashboard.web import create_app

        app = create_app(skills_path, traj_path)
        client = TestClient(app)

        resp = client.get("/api/trajectories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["task"] == "Solve a math problem"
        assert data[0]["reward"] == 0.95
        assert data[0]["steps"] == 1
    finally:
        shutil.rmtree(skills_path)
        shutil.rmtree(traj_path)


def test_web_api_stats():
    skills_path, traj_path, _, _ = _setup()
    try:
        from fastapi.testclient import TestClient
        from arise.dashboard.web import create_app

        app = create_app(skills_path, traj_path)
        client = TestClient(app)

        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] == 1
        assert data["total_skills"] == 1
        assert data["avg_success_rate"] == 0.8
    finally:
        shutil.rmtree(skills_path)
        shutil.rmtree(traj_path)


def test_web_index_html():
    skills_path, traj_path, _, _ = _setup()
    try:
        from fastapi.testclient import TestClient
        from arise.dashboard.web import create_app

        app = create_app(skills_path, traj_path)
        client = TestClient(app)

        resp = client.get("/")
        assert resp.status_code == 200
        assert "ARISE Dashboard" in resp.text
        assert "/api/skills" in resp.text
    finally:
        shutil.rmtree(skills_path)
        shutil.rmtree(traj_path)


def test_web_empty_data():
    skills_path = tempfile.mkdtemp()
    traj_path = tempfile.mkdtemp()
    try:
        from fastapi.testclient import TestClient
        from arise.dashboard.web import create_app

        app = create_app(skills_path, traj_path)
        client = TestClient(app)

        assert client.get("/api/skills").json() == []
        assert client.get("/api/trajectories").json() == []
        stats = client.get("/api/stats").json()
        assert stats["total_skills"] == 0
    finally:
        shutil.rmtree(skills_path)
        shutil.rmtree(traj_path)
