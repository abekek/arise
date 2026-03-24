from fastapi import APIRouter, HTTPException
from ..registry import AgentRegistry

router = APIRouter(prefix="/api", tags=["evolutions"])
_registry: AgentRegistry | None = None


def init(registry: AgentRegistry):
    global _registry
    _registry = registry


@router.get("/agents/{agent_id}/evolutions")
def list_evolutions(agent_id: str):
    agent = _registry._agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    arise = agent.get("arise")
    if arise is None:
        return []
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "gaps_detected": r.gaps_detected,
            "tools_synthesized": r.tools_synthesized,
            "tools_promoted": r.tools_promoted,
            "tools_rejected": r.tools_rejected,
            "duration_ms": r.duration_ms,
            "cost_usd": r.cost_usd,
        }
        for r in arise.evolution_history
    ]
