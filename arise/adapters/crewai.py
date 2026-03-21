"""CrewAI adapter for ARISE.

Converts ARISE ToolSpec objects into CrewAI-compatible tools and wraps
a CrewAI Crew so it conforms to ARISE's agent_fn interface.

Usage:
    from arise import ARISE
    from arise.adapters import crewai_adapter
    from crewai import Agent, Task, Crew

    agent = Agent(role="Assistant", goal="Help", backstory="Helpful AI")
    task = Task(description="{task}", agent=agent, expected_output="Answer")
    crew = Crew(agents=[agent], tasks=[task])

    agent_fn = crewai_adapter(crew)
    arise = ARISE(agent_fn=agent_fn, reward_fn=my_reward_fn)
"""

from __future__ import annotations

from typing import Any, Callable

from arise.types import ToolSpec


def _check_crewai_installed() -> None:
    """Raise a helpful ImportError if crewai is not installed."""
    try:
        import crewai  # noqa: F401
    except ImportError:
        raise ImportError(
            "The crewai package is required for the CrewAI adapter. "
            "Install it with: pip install crewai"
        ) from None


# JSON Schema type string -> Python type mapping
_SCHEMA_TYPE_TO_PYTHON: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _toolspec_to_crewai_tool(tool_spec: ToolSpec) -> Any:
    """Convert an ARISE ToolSpec into a CrewAI @tool-decorated callable.

    CrewAI discovers tool metadata from the @tool decorator which reads:
    - Function name (__name__)
    - Docstring (__doc__)
    - Type annotations (__annotations__)
    - inspect.signature parameters
    """
    from crewai.tools import tool

    params_schema = tool_spec.parameters
    properties = params_schema.get("properties", {})
    required = set(params_schema.get("required", []))

    # Build parameter annotations dict
    annotations: dict[str, type] = {}
    for param_name, param_schema in properties.items():
        py_type = _SCHEMA_TYPE_TO_PYTHON.get(param_schema.get("type", "string"), str)
        annotations[param_name] = py_type
    annotations["return"] = str

    # Build parameter string for exec-based function creation
    param_parts: list[str] = []
    for param_name, param_schema in properties.items():
        if param_name in required:
            param_parts.append(param_name)
        else:
            default = param_schema.get("default")
            param_parts.append(f"{param_name}={default!r}")

    param_str = ", ".join(param_parts)

    func_name = tool_spec.name
    safe_name = func_name.replace("-", "_").replace(" ", "_")
    if not safe_name.isidentifier():
        safe_name = f"tool_{safe_name}"

    func_code = f"def {safe_name}({param_str}):\n    return _original_fn({', '.join(f'{p}={p}' for p in properties)})"

    namespace: dict[str, Any] = {"_original_fn": tool_spec.fn}
    exec(func_code, namespace)  # noqa: S102
    wrapper = namespace[safe_name]

    wrapper.__name__ = safe_name
    wrapper.__qualname__ = safe_name
    wrapper.__doc__ = tool_spec.description
    wrapper.__annotations__ = annotations

    # Apply the CrewAI @tool decorator
    decorated = tool(wrapper)
    return decorated


def crewai_adapter(
    crew: Any,
    *,
    task_template: str | None = None,
) -> Callable[[str, list[ToolSpec]], str]:
    """Create an ARISE-compatible agent_fn backed by a CrewAI Crew.

    The adapter injects ARISE tools into the crew's agents before each
    kickoff. The task description is passed via the ``{task}`` placeholder
    in crew task descriptions.

    Args:
        crew: A ``crewai.Crew`` instance.
        task_template: Optional template for the task input key.
            Defaults to ``"task"``.

    Returns:
        A callable with signature ``(task: str, tools: list[ToolSpec]) -> str``
        suitable for passing as ``agent_fn`` to :class:`arise.ARISE`.

    Raises:
        ImportError: If ``crewai`` is not installed.
    """
    _check_crewai_installed()

    input_key = task_template or "task"

    def agent_fn(task: str, tools: list[ToolSpec]) -> str:
        # Convert ARISE ToolSpecs to CrewAI tools
        crewai_tools = [_toolspec_to_crewai_tool(ts) for ts in tools]

        # Inject tools into all agents in the crew
        for agent in crew.agents:
            existing_tools = list(agent.tools) if agent.tools else []
            agent.tools = existing_tools + crewai_tools

        try:
            result = crew.kickoff(inputs={input_key: task})
            return str(result)
        finally:
            # Remove injected tools to avoid accumulation across calls
            for agent in crew.agents:
                if agent.tools:
                    agent.tools = [
                        t for t in agent.tools if t not in crewai_tools
                    ]

    return agent_fn
