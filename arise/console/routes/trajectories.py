from fastapi import APIRouter, HTTPException, Query
from ..registry import AgentRegistry

router = APIRouter(prefix="/api", tags=["trajectories"])
_registry: AgentRegistry | None = None


def init(registry: AgentRegistry):
    global _registry
    _registry = registry


@router.get("/agents/{agent_id}/trajectories")
def list_trajectories(agent_id: str, limit: int = Query(20, le=100)):
    agent = _registry._agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    arise = agent.get("arise")
    if arise is None or not hasattr(arise, 'trajectory_store') or arise.trajectory_store is None:
        return []
    trajs = arise.trajectory_store.get_recent(limit)
    return [
        {
            "task": t.task,
            "reward": t.reward,
            "status": "ok" if t.reward >= 0.5 else "fail",
            "steps_count": len(t.steps),
            "skills_count": t.skill_library_version,
            "outcome": t.outcome[:500],
            "steps": [
                {
                    "action": s.action,
                    "action_input": s.action_input,
                    "result": s.result[:300],
                    "error": s.error,
                    "latency_ms": s.latency_ms,
                }
                for s in t.steps
            ],
            "timestamp": t.timestamp.isoformat(),
        }
        for t in trajs
    ]
