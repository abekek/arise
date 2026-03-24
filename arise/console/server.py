from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .registry import AgentRegistry
from .routes import agents, settings as settings_routes


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
    app.include_router(agents.router)

    settings_routes.init(data_dir)
    app.include_router(settings_routes.router)

    return app


def run_console(data_dir: str = "~/.arise/console", port: int = 8080, host: str = "0.0.0.0"):
    """Run the ARISE Console server."""
    import uvicorn
    app = create_console_app(data_dir=data_dir)
    print(f"\n  ARISE Console running at http://localhost:{port}\n")
    uvicorn.run(app, host=host, port=port)
