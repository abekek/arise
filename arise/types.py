from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

_VALID_SKILL_NAME = re.compile(r'^[a-z_][a-z0-9_]*$')


class SkillStatus(Enum):
    TESTING = "testing"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class SkillOrigin(Enum):
    MANUAL = "manual"
    SYNTHESIZED = "synthesized"
    REFINED = "refined"
    COMPOSED = "composed"
    PATCHED = "patched"


@dataclass
class Skill:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    implementation: str = ""
    test_suite: str = ""
    version: int = 1
    status: SkillStatus = SkillStatus.TESTING
    origin: SkillOrigin = SkillOrigin.SYNTHESIZED
    parent_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    # Performance tracking
    invocation_count: int = 0
    success_count: int = 0
    avg_latency_ms: float = 0.0
    error_log: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.name and not _VALID_SKILL_NAME.match(self.name):
            raise ValueError(
                f"Invalid skill name '{self.name}': must match [a-z_][a-z0-9_]* "
                f"(lowercase, underscores, no spaces or special characters)"
            )

    @property
    def success_rate(self) -> float:
        if self.invocation_count == 0:
            return 0.0
        return self.success_count / self.invocation_count

    def to_callable(self) -> Callable:
        namespace: dict[str, Any] = {}
        exec(self.implementation, namespace)  # noqa: S102
        return namespace[self.name]

    def to_tool_spec(self) -> ToolSpec:
        fn = self.to_callable()
        parameters = _extract_parameters(fn)
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=parameters,
            fn=fn,
            skill_id=self.id,
        )


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for parameters
    fn: Callable
    skill_id: str | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.fn(*args, **kwargs)


def _extract_parameters(fn: Callable) -> dict[str, Any]:
    import inspect
    sig = inspect.signature(fn)
    hints = {}
    try:
        hints = fn.__annotations__ if hasattr(fn, "__annotations__") else {}
    except Exception:
        pass

    type_map = {
        str: "string", int: "integer", float: "number", bool: "boolean",
        list: "array", dict: "object",
    }

    # Also map string type names for exec'd functions where annotations are strings
    str_type_map = {
        "str": "string", "int": "integer", "float": "number", "bool": "boolean",
        "list": "array", "dict": "object",
        "list[dict]": "array", "list[str]": "array", "list[int]": "array",
    }

    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        prop: dict[str, Any] = {}
        hint = hints.get(name)
        if hint in type_map:
            prop["type"] = type_map[hint]
        elif isinstance(hint, str) and hint in str_type_map:
            prop["type"] = str_type_map[hint]
        elif param.annotation is not inspect.Parameter.empty:
            ann = param.annotation
            if ann in type_map:
                prop["type"] = type_map[ann]
            elif isinstance(ann, str) and ann in str_type_map:
                prop["type"] = str_type_map[ann]
            else:
                prop["type"] = "string"
        else:
            prop["type"] = "string"
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            prop["default"] = param.default
        properties[name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


@dataclass
class Step:
    observation: str
    reasoning: str
    action: str
    action_input: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    error: str | None = None
    latency_ms: float = 0.0


@dataclass
class Trajectory:
    task: str
    steps: list[Step] = field(default_factory=list)
    outcome: str = ""
    reward: float = 0.0
    skill_library_version: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GapAnalysis:
    description: str
    evidence: list[str] = field(default_factory=list)
    suggested_name: str = ""
    suggested_signature: str = ""
    similar_existing: list[str] = field(default_factory=list)


@dataclass
class TestResult:
    passed: bool
    test_name: str
    error: str | None = None
    stdout: str = ""
    execution_time_ms: float = 0.0


class SkillValidationError(Exception):
    """Raised when a pulled skill fails sandbox validation."""
    pass


@dataclass
class EvolutionReport:
    timestamp: datetime = field(default_factory=datetime.now)
    gaps_detected: list[str] = field(default_factory=list)
    tools_synthesized: list[str] = field(default_factory=list)
    tools_promoted: list[str] = field(default_factory=list)
    tools_rejected: list[dict[str, str]] = field(default_factory=list)
    duration_ms: float = 0.0
    cost_usd: float = 0.0


@dataclass
class SandboxResult:
    success: bool
    test_results: list[TestResult] = field(default_factory=list)
    total_passed: int = 0
    total_failed: int = 0
    stdout: str = ""
    stderr: str = ""
