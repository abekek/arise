from pydantic import BaseModel, Field
from datetime import datetime


class AgentCreate(BaseModel):
    name: str
    model: str = "gpt-4o-mini"
    system_prompt: str = ""
    tasks: list[str] = []
    reward_function: str = "task_success"  # preset name
    allowed_imports: list[str] | None = None
    sandbox_backend: str = "subprocess"
    failure_threshold: int = 5
    # LLM provider config
    api_key: str | None = None  # OpenAI/Anthropic key
    aws_profile: str | None = None
    aws_region: str = "us-east-1"


class AgentUpdate(BaseModel):
    system_prompt: str | None = None
    tasks: list[str] | None = None
    failure_threshold: int | None = None
    allowed_imports: list[str] | None = None


class AgentSummary(BaseModel):
    id: str
    name: str
    model: str
    status: str  # running, stopped, evolving
    skills_count: int
    success_rate: float
    episodes: int
    evolutions: int
    created_at: str


class AgentDetail(AgentSummary):
    system_prompt: str
    tasks: list[str]
    reward_function: str
    allowed_imports: list[str] | None
    sandbox_backend: str
    failure_threshold: int
    library_version: int
    avg_latency_ms: float


class SkillSummary(BaseModel):
    id: str
    name: str
    description: str
    status: str
    origin: str
    success_rate: float
    invocation_count: int
    created_at: str


class SkillDetail(SkillSummary):
    implementation: str
    test_suite: str
    version: int
    avg_latency_ms: float
    parent_id: str | None


class TrajectorySummary(BaseModel):
    id: str
    task: str
    reward: float
    status: str  # ok or fail
    steps_count: int
    skills_count: int
    timestamp: str


class TrajectoryDetail(TrajectorySummary):
    outcome: str
    steps: list[dict]
    metadata: dict


class EvolutionSummary(BaseModel):
    timestamp: str
    gaps_detected: list[str]
    tools_synthesized: list[str]
    tools_promoted: list[str]
    tools_rejected: list[dict]
    duration_ms: float
    cost_usd: float


class SettingsRead(BaseModel):
    default_model: str
    default_sandbox: str
    default_failure_threshold: int
    default_allowed_imports: list[str] | None
    # Keys are stored but returned masked
    openai_key_set: bool
    anthropic_key_set: bool
    aws_profile: str | None
    aws_region: str


class SettingsUpdate(BaseModel):
    default_model: str | None = None
    default_sandbox: str | None = None
    default_failure_threshold: int | None = None
    default_allowed_imports: list[str] | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    aws_profile: str | None = None
    aws_region: str | None = None


class RunTaskRequest(BaseModel):
    task: str


class RunTaskResponse(BaseModel):
    result: str
    reward: float
    episode: int
    skills_count: int
