import json
import os
from fastapi import APIRouter
from ..schemas import SettingsRead, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])
_settings_path: str = ""


def init(data_dir: str):
    global _settings_path
    _settings_path = os.path.join(os.path.expanduser(data_dir), "settings.json")


def _load() -> dict:
    if os.path.exists(_settings_path):
        with open(_settings_path) as f:
            return json.load(f)
    return {}


def _save(data: dict):
    with open(_settings_path, "w") as f:
        json.dump(data, f, indent=2)


@router.get("")
def get_settings() -> SettingsRead:
    s = _load()
    return SettingsRead(
        default_model=s.get("default_model", "gpt-4o-mini"),
        default_sandbox=s.get("default_sandbox", "subprocess"),
        default_failure_threshold=s.get("default_failure_threshold", 5),
        default_allowed_imports=s.get("default_allowed_imports"),
        openai_key_set=bool(s.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")),
        anthropic_key_set=bool(s.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")),
        aws_profile=s.get("aws_profile"),
        aws_region=s.get("aws_region", "us-east-1"),
    )


@router.put("")
def update_settings(req: SettingsUpdate):
    s = _load()
    for field, value in req.model_dump(exclude_none=True).items():
        s[field] = value
        # Also set env vars for API keys
        if field == "openai_api_key" and value:
            os.environ["OPENAI_API_KEY"] = value
        elif field == "anthropic_api_key" and value:
            os.environ["ANTHROPIC_API_KEY"] = value
    _save(s)
    return get_settings()
