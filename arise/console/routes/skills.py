from fastapi import APIRouter, HTTPException
from ..registry import AgentRegistry

router = APIRouter(prefix="/api", tags=["skills"])
_registry: AgentRegistry | None = None


def init(registry: AgentRegistry):
    global _registry
    _registry = registry


@router.get("/agents/{agent_id}/skills")
def list_skills(agent_id: str):
    arise = _registry.get_arise(agent_id)
    if arise is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "status": s.status.value,
            "origin": s.origin.value,
            "success_rate": s.success_rate,
            "invocation_count": s.invocation_count,
            "created_at": s.created_at.isoformat(),
        }
        for s in arise._skill_store.get_active_skills()
    ]


@router.get("/skills/{skill_id}")
def get_skill(skill_id: str, agent_id: str | None = None):
    # Search across all agents if agent_id not provided
    for aid, agent in _registry._agents.items():
        if agent_id and aid != agent_id:
            continue
        arise = agent.get("arise")
        if arise is None:
            continue
        if hasattr(arise, 'skill_library') and arise.skill_library:
            skill = arise.skill_library.get_skill(skill_id)
            if skill:
                return {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "status": skill.status.value,
                    "origin": skill.origin.value,
                    "success_rate": skill.success_rate,
                    "invocation_count": skill.invocation_count,
                    "implementation": skill.implementation,
                    "test_suite": skill.test_suite,
                    "version": skill.version,
                    "avg_latency_ms": skill.avg_latency_ms,
                    "parent_id": skill.parent_id,
                    "created_at": skill.created_at.isoformat(),
                }
    raise HTTPException(status_code=404, detail="Skill not found")


@router.delete("/skills/{skill_id}", status_code=204)
def deprecate_skill(skill_id: str):
    for agent in _registry._agents.values():
        arise = agent.get("arise")
        if arise and hasattr(arise, 'skill_library') and arise.skill_library:
            skill = arise.skill_library.get_skill(skill_id)
            if skill:
                arise.skill_library.deprecate(skill_id)
                return
    raise HTTPException(status_code=404, detail="Skill not found")
