from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime

from arise.types import Step, Trajectory


class TrajectoryStore:
    def __init__(self, path: str = "./arise_trajectories"):
        self.path = path
        os.makedirs(path, exist_ok=True)
        self._db_path = os.path.join(path, "trajectories.db")
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS trajectories (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                steps TEXT NOT NULL,
                outcome TEXT,
                reward REAL DEFAULT 0.0,
                skill_library_version INTEGER DEFAULT 0,
                timestamp TEXT,
                metadata TEXT DEFAULT '{}'
            );
        """)
        self._conn.commit()

    def save(self, trajectory: Trajectory) -> str:
        tid = str(uuid.uuid4())[:8]
        steps_json = json.dumps([
            {
                "observation": s.observation,
                "reasoning": s.reasoning,
                "action": s.action,
                "action_input": s.action_input,
                "result": s.result,
                "error": s.error,
                "latency_ms": s.latency_ms,
            }
            for s in trajectory.steps
        ])
        self._conn.execute(
            """INSERT INTO trajectories (id, task, steps, outcome, reward,
               skill_library_version, timestamp, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tid, trajectory.task, steps_json, trajectory.outcome,
                trajectory.reward, trajectory.skill_library_version,
                trajectory.timestamp.isoformat(),
                json.dumps(trajectory.metadata),
            ),
        )
        self._conn.commit()
        return tid

    def get_recent(self, n: int = 20) -> list[Trajectory]:
        rows = self._conn.execute(
            "SELECT * FROM trajectories ORDER BY timestamp DESC LIMIT ?", (n,)
        ).fetchall()
        return [self._row_to_trajectory(r) for r in rows]

    def get_failures(self, n: int = 20, threshold: float = 0.5) -> list[Trajectory]:
        rows = self._conn.execute(
            "SELECT * FROM trajectories WHERE reward < ? ORDER BY timestamp DESC LIMIT ?",
            (threshold, n),
        ).fetchall()
        return [self._row_to_trajectory(r) for r in rows]

    def success_rate(self, window: int = 50) -> float:
        rows = self._conn.execute(
            "SELECT reward FROM trajectories ORDER BY timestamp DESC LIMIT ?",
            (window,),
        ).fetchall()
        if not rows:
            return 0.0
        return sum(1 for r in rows if r["reward"] >= 0.5) / len(rows)

    def _row_to_trajectory(self, row: sqlite3.Row) -> Trajectory:
        steps_raw = json.loads(row["steps"])
        steps = [Step(**s) for s in steps_raw]
        return Trajectory(
            task=row["task"],
            steps=steps,
            outcome=row["outcome"] or "",
            reward=row["reward"],
            skill_library_version=row["skill_library_version"],
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
