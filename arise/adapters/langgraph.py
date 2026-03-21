"""LangGraph adapter for ARISE.

Converts ARISE ToolSpec objects into LangGraph-compatible tools (using
``@tool`` from ``langchain_core.tools``) and wraps a compiled LangGraph
graph so it conforms to ARISE's agent_fn interface.

Usage:
    from arise import ARISE
    from arise.adapters import langgraph_adapter
    from langgraph.prebuilt import create_react_agent
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o")
    graph = create_react_agent(llm, tools=[])

    agent_fn = langgraph_adapter(graph)
    arise = ARISE(agent_fn=agent_fn, reward_fn=my_reward_fn)
"""

from __future__ import annotations

from typing import Any, Callable

from arise.types import ToolSpec


def _check_langgraph_installed() -> None:
    """Raise a helpful ImportError if langgraph is not installed."""
    try:
        import langgraph  # noqa: F401
    except ImportError:
        raise ImportError(
            "The langgraph package is required for the LangGraph adapter. "
            "Install it with: pip install langgraph langchain-core"
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


def _toolspec_to_langgraph_tool(tool_spec: ToolSpec) -> Any:
    """Convert an ARISE ToolSpec into a LangGraph-compatible tool.

    Uses ``@tool`` from ``langchain_core.tools`` which discovers metadata
    from the function name, docstring, and type annotations.
    """
    from langchain_core.tools import tool

    params_schema = tool_spec.parameters
    properties = params_schema.get("properties", {})
    required = set(params_schema.get("required", []))

    # Build parameter annotations
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

    func_code = (
        f"def {safe_name}({param_str}):\n"
        f"    return _original_fn({', '.join(f'{p}={p}' for p in properties)})"
    )

    namespace: dict[str, Any] = {"_original_fn": tool_spec.fn}
    exec(func_code, namespace)  # noqa: S102
    wrapper = namespace[safe_name]

    wrapper.__name__ = safe_name
    wrapper.__qualname__ = safe_name
    wrapper.__doc__ = tool_spec.description
    wrapper.__annotations__ = annotations

    # Apply the LangGraph @tool decorator
    decorated = tool(wrapper)
    return decorated


def langgraph_adapter(
    graph: Any | None = None,
    *,
    model: Any | None = None,
    system_prompt: str | None = None,
    **graph_kwargs: Any,
) -> Callable[[str, list[ToolSpec]], str]:
    """Create an ARISE-compatible agent_fn backed by a LangGraph graph.

    Can be called in two ways:

    1. With an existing compiled graph (preferred)::

        graph = create_react_agent(llm, tools=[])
        agent_fn = langgraph_adapter(graph)

    2. With a model to create a react agent on the fly::

        agent_fn = langgraph_adapter(model=ChatOpenAI(...), system_prompt="...")

    Args:
        graph: A compiled LangGraph graph (``CompiledGraph``). If provided,
            ARISE tools will be bound to the graph's tool node.
        model: A LangChain chat model instance. Used to create a new
            react agent when ``graph`` is not provided.
        system_prompt: Optional system prompt for the agent.
        **graph_kwargs: Additional keyword arguments forwarded to
            ``create_react_agent``.

    Returns:
        A callable with signature ``(task: str, tools: list[ToolSpec]) -> str``
        suitable for passing as ``agent_fn`` to :class:`arise.ARISE`.

    Raises:
        ImportError: If ``langgraph`` is not installed.
        ValueError: If neither ``graph`` nor ``model`` is provided.
    """
    _check_langgraph_installed()

    if graph is None and model is None:
        raise ValueError(
            "Either 'graph' (a compiled LangGraph graph) or 'model' "
            "(a LangChain chat model) must be provided."
        )

    def agent_fn(task: str, tools: list[ToolSpec]) -> str:
        from langgraph.prebuilt import create_react_agent

        # Convert ARISE ToolSpecs to LangGraph tools
        lg_tools = [_toolspec_to_langgraph_tool(ts) for ts in tools]

        if graph is not None:
            # Rebuild the react agent with merged tools.
            # LangGraph compiled graphs are immutable, so we extract the
            # model and create a new graph with ARISE tools included.
            graph_model = getattr(graph, "model", model)
            existing_tools = list(getattr(graph, "tools", []) or [])
            all_tools = existing_tools + lg_tools

            kwargs: dict[str, Any] = {**graph_kwargs}
            if system_prompt is not None:
                kwargs["state_modifier"] = system_prompt
            elif hasattr(graph, "state_modifier"):
                kwargs["state_modifier"] = graph.state_modifier

            agent_graph = create_react_agent(graph_model, all_tools, **kwargs)
        else:
            kwargs = {**graph_kwargs}
            if system_prompt is not None:
                kwargs["state_modifier"] = system_prompt
            agent_graph = create_react_agent(model, lg_tools, **kwargs)

        result = agent_graph.invoke(
            {"messages": [("user", task)]}
        )

        # Extract final message content from the graph result
        messages = result.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, "content"):
                return str(last_message.content)
            return str(last_message)
        return str(result)

    return agent_fn
