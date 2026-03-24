from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .registry import AgentRegistry
from .routes import agents, skills, trajectories, evolutions
from . import ws


def create_console_app(data_dir: str = "~/.arise/console") -> FastAPI:
    app = FastAPI(title="ARISE Console", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registry = AgentRegistry(data_dir=data_dir)

    agents.init(registry)
    skills.init(registry)
    trajectories.init(registry)
    evolutions.init(registry)
    ws.init(registry)

    app.include_router(agents.router)
    app.include_router(skills.router)
    app.include_router(trajectories.router)
    app.include_router(evolutions.router)
    app.include_router(ws.router)

    return app
