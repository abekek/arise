"""Background agent runner that emits events over WebSocket."""
import asyncio
import json
import time
from datetime import datetime
from typing import Any

from arise import ARISE


class AgentRunner:
    """Wraps ARISE.run() to emit structured events for WebSocket clients."""

    def __init__(self, arise: ARISE, agent_id: str):
        self.arise = arise
        self.agent_id = agent_id
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.remove(q)

    def _emit(self, event: dict):
        event["agent_id"] = self.agent_id
        event["timestamp"] = datetime.now().isoformat()
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def run_task(self, task: str) -> str:
        episode = self.arise.stats.get("episodes_run", 0) + 1
        self._emit({"type": "episode_start", "episode": episode, "task": task})

        # Monkey-patch evolve to emit events
        original_evolve = self.arise.evolve
        def patched_evolve():
            self._emit({"type": "evolution_start", "reason": "failure_streak"})
            original_evolve()
            report = self.arise.last_evolution
            if report:
                for gap in report.gaps_detected:
                    self._emit({"type": "gap_detected", "description": gap})
                for name in report.tools_promoted:
                    self._emit({"type": "skill_promoted", "name": name})
                for rej in report.tools_rejected:
                    self._emit({"type": "skill_rejected", **rej})
                self._emit({
                    "type": "evolution_end",
                    "promoted": report.tools_promoted,
                    "rejected": report.tools_rejected,
                    "duration_ms": report.duration_ms,
                })
        self.arise.evolve = patched_evolve

        try:
            result = self.arise.run(task)
        finally:
            self.arise.evolve = original_evolve

        stats = self.arise.stats
        reward = 0.0
        # Use trajectory store to get last reward
        if hasattr(self.arise, 'trajectory_store') and self.arise.trajectory_store:
            recent = self.arise.trajectory_store.get_recent(1)
            if recent:
                reward = recent[0].reward

        self._emit({
            "type": "episode_end",
            "episode": episode,
            "reward": reward,
            "status": "ok" if reward >= 0.5 else "fail",
            "skills": len(self.arise.skills),
            "result_preview": result[:200],
        })

        return result
