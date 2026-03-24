from fastapi import APIRouter, HTTPException
from ..schemas import AgentCreate, AgentUpdate, RunTaskRequest, RunTaskResponse
from ..registry import AgentRegistry

router = APIRouter(prefix="/api/agents", tags=["agents"])
_registry: AgentRegistry | None = None


def init(registry: AgentRegistry):
    global _registry
    _registry = registry


@router.get("")
def list_agents():
    return _registry.list()


@router.post("", status_code=201)
def create_agent(req: AgentCreate):
    return _registry.create(req)


@router.get("/{agent_id}")
def get_agent(agent_id: str):
    agent = _registry.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str):
    _registry.delete(agent_id)


@router.put("/{agent_id}/config")
def update_agent(agent_id: str, req: AgentUpdate):
    agent = _registry.update(agent_id, req)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/run")
def run_task(agent_id: str, req: RunTaskRequest):
    arise = _registry.get_arise(agent_id)
    if arise is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _registry.set_status(agent_id, "running")
    try:
        result = arise.run(req.task)
        return RunTaskResponse(
            result=result,
            reward=arise.last_evolution.cost_usd if arise.last_evolution else 0.0,
            episode=arise.stats.get("episodes_run", 0),
            skills_count=len(arise.skills),
        )
    finally:
        _registry.set_status(agent_id, "stopped")
