import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .registry import AgentRegistry
from .runner import AgentRunner

router = APIRouter()
_registry: AgentRegistry | None = None
_runners: dict[str, AgentRunner] = {}


def init(registry: AgentRegistry):
    global _registry
    _registry = registry


def get_runner(agent_id: str) -> AgentRunner | None:
    if agent_id in _runners:
        return _runners[agent_id]
    arise = _registry.get_arise(agent_id)
    if arise is None:
        return None
    runner = AgentRunner(arise, agent_id)
    _runners[agent_id] = runner
    return runner


@router.websocket("/ws/agents/{agent_id}/live")
async def agent_live(websocket: WebSocket, agent_id: str):
    await websocket.accept()

    runner = get_runner(agent_id)
    if runner is None:
        await websocket.close(code=4004, reason="Agent not found")
        return

    queue = runner.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    finally:
        runner.unsubscribe(queue)
