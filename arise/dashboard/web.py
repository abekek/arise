from __future__ import annotations

import threading
import webbrowser

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from arise.skills.library import SkillLibrary
from arise.trajectory.store import TrajectoryStore

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<title>ARISE Dashboard</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; background: #0d1117; color: #c9d1d9; }
  h1 { color: #58a6ff; }
  h2 { color: #8b949e; margin-top: 2rem; }
  table { border-collapse: collapse; width: 100%%; margin-bottom: 2rem; }
  th, td { text-align: left; padding: 0.5rem 1rem; border-bottom: 1px solid #21262d; }
  th { background: #161b22; color: #58a6ff; }
  tr:hover { background: #161b22; }
  .stat-box { display: inline-block; background: #161b22; padding: 1rem 1.5rem;
              border-radius: 8px; margin: 0.5rem; text-align: center; }
  .stat-value { font-size: 1.5rem; font-weight: bold; color: #58a6ff; }
  .stat-label { font-size: 0.85rem; color: #8b949e; }
</style>
</head>
<body>
<h1>ARISE Dashboard</h1>
<div id="stats"></div>
<h2>Skills</h2>
<table id="skills-table"><thead><tr>
  <th>Name</th><th>Status</th><th>Success Rate</th><th>Invocations</th><th>Origin</th>
</tr></thead><tbody></tbody></table>
<h2>Recent Trajectories</h2>
<table id="traj-table"><thead><tr>
  <th>Task</th><th>Reward</th><th>Steps</th><th>Time</th>
</tr></thead><tbody></tbody></table>
<script>
async function load() {
  const stats = await (await fetch('/api/stats')).json();
  document.getElementById('stats').innerHTML = [
    ['Version', stats.library_version],
    ['Active', stats.active],
    ['Testing', stats.testing],
    ['Deprecated', stats.deprecated],
    ['Total', stats.total_skills],
    ['Avg Success', (stats.avg_success_rate * 100).toFixed(1) + '%%'],
  ].map(([l, v]) => `<div class="stat-box"><div class="stat-value">${v}</div><div class="stat-label">${l}</div></div>`).join('');

  const skills = await (await fetch('/api/skills')).json();
  document.querySelector('#skills-table tbody').innerHTML = skills.map(s =>
    `<tr><td>${s.name}</td><td>${s.status}</td><td>${(s.success_rate * 100).toFixed(1)}%%</td><td>${s.invocations}</td><td>${s.origin}</td></tr>`
  ).join('');

  const trajs = await (await fetch('/api/trajectories')).json();
  document.querySelector('#traj-table tbody').innerHTML = trajs.map(t =>
    `<tr><td>${t.task.slice(0, 60)}</td><td>${t.reward.toFixed(2)}</td><td>${t.steps}</td><td>${t.timestamp}</td></tr>`
  ).join('');
}
load();
</script>
</body>
</html>
"""


def create_app(skills_path: str, trajectories_path: str) -> FastAPI:
    app = FastAPI(title="ARISE Dashboard")
    lib = SkillLibrary(skills_path)
    store = TrajectoryStore(trajectories_path)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _HTML_TEMPLATE

    @app.get("/api/skills")
    def api_skills():
        all_rows = lib._conn.execute(
            "SELECT * FROM skills ORDER BY status, name"
        ).fetchall()
        result = []
        for row in all_rows:
            skill = lib._row_to_skill(row)
            result.append({
                "id": skill.id,
                "name": skill.name,
                "status": skill.status.value,
                "success_rate": round(skill.success_rate, 3),
                "invocations": skill.invocation_count,
                "origin": skill.origin.value,
                "description": skill.description,
            })
        return result

    @app.get("/api/trajectories")
    def api_trajectories():
        trajectories = store.get_recent(20)
        return [
            {
                "task": t.task,
                "reward": t.reward,
                "steps": len(t.steps),
                "outcome": t.outcome,
                "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M"),
            }
            for t in trajectories
        ]

    @app.get("/api/stats")
    def api_stats():
        return lib.stats()

    return app


def run_web(skills_path: str, trajectories_path: str, port: int = 8501) -> None:
    import uvicorn

    app = create_app(skills_path, trajectories_path)
    url = f"http://localhost:{port}"
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
