"""Tests for the LangGraph adapter.

All tests mock the langgraph/langchain packages so they run without them installed.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from arise.types import ToolSpec


# ---------------------------------------------------------------------------
# Fixtures: mock the langgraph and langchain packages
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_langgraph(monkeypatch):
    """Inject mock langgraph and langchain_core packages into sys.modules."""
    langgraph_mod = types.ModuleType("langgraph")
    langgraph_prebuilt_mod = types.ModuleType("langgraph.prebuilt")
    langchain_core_mod = types.ModuleType("langchain_core")
    langchain_core_tools_mod = types.ModuleType("langchain_core.tools")

    # langchain_core.tools.tool: decorator that returns the function as-is
    def fake_tool_decorator(fn):
        fn._is_langgraph_tool = True
        return fn

    langchain_core_tools_mod.tool = fake_tool_decorator

    # langgraph.prebuilt.create_react_agent: mock
    mock_create_react_agent = MagicMock()
    langgraph_prebuilt_mod.create_react_agent = mock_create_react_agent

    langgraph_mod.prebuilt = langgraph_prebuilt_mod

    monkeypatch.setitem(sys.modules, "langgraph", langgraph_mod)
    monkeypatch.setitem(sys.modules, "langgraph.prebuilt", langgraph_prebuilt_mod)
    monkeypatch.setitem(sys.modules, "langchain_core", langchain_core_mod)
    monkeypatch.setitem(sys.modules, "langchain_core.tools", langchain_core_tools_mod)

    return mock_create_react_agent


# ---------------------------------------------------------------------------
# Helper to build simple ToolSpec objects
# ---------------------------------------------------------------------------

def _make_tool_spec(name: str = "greet", description: str = "Say hello") -> ToolSpec:
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    return ToolSpec(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
        fn=greet,
    )


def _make_tool_spec_with_default() -> ToolSpec:
    def add(a: int, b: int = 0) -> int:
        return a + b

    return ToolSpec(
        name="add",
        description="Add two numbers.",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer", "default": 0},
            },
            "required": ["a"],
        },
        fn=add,
    )


# ---------------------------------------------------------------------------
# Tests: _toolspec_to_langgraph_tool
# ---------------------------------------------------------------------------

class TestToolSpecConversion:
    def test_basic_conversion(self, mock_langgraph):
        from arise.adapters.langgraph import _toolspec_to_langgraph_tool

        ts = _make_tool_spec()
        lg_tool = _toolspec_to_langgraph_tool(ts)

        assert callable(lg_tool)
        assert lg_tool.__name__ == "greet"
        assert lg_tool.__doc__ == "Say hello"
        assert hasattr(lg_tool, "_is_langgraph_tool")

    def test_preserves_annotations(self, mock_langgraph):
        from arise.adapters.langgraph import _toolspec_to_langgraph_tool

        ts = _make_tool_spec()
        lg_tool = _toolspec_to_langgraph_tool(ts)

        assert lg_tool.__annotations__["name"] is str
        assert lg_tool.__annotations__["return"] is str

    def test_tool_is_callable(self, mock_langgraph):
        from arise.adapters.langgraph import _toolspec_to_langgraph_tool

        ts = _make_tool_spec()
        lg_tool = _toolspec_to_langgraph_tool(ts)

        result = lg_tool(name="World")
        assert result == "Hello, World!"

    def test_tool_with_defaults(self, mock_langgraph):
        from arise.adapters.langgraph import _toolspec_to_langgraph_tool

        ts = _make_tool_spec_with_default()
        lg_tool = _toolspec_to_langgraph_tool(ts)

        assert lg_tool(a=3) == 3
        assert lg_tool(a=3, b=7) == 10

    def test_annotations_for_numeric_types(self, mock_langgraph):
        from arise.adapters.langgraph import _toolspec_to_langgraph_tool

        ts = _make_tool_spec_with_default()
        lg_tool = _toolspec_to_langgraph_tool(ts)

        assert lg_tool.__annotations__["a"] is int
        assert lg_tool.__annotations__["b"] is int

    def test_hyphenated_name_sanitized(self, mock_langgraph):
        from arise.adapters.langgraph import _toolspec_to_langgraph_tool

        ts = _make_tool_spec(name="my-tool", description="A tool with hyphens")
        lg_tool = _toolspec_to_langgraph_tool(ts)

        assert lg_tool.__name__ == "my_tool"


# ---------------------------------------------------------------------------
# Tests: langgraph_adapter with model parameter
# ---------------------------------------------------------------------------

class TestLangGraphAdapterWithModel:
    def test_creates_agent_fn(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_model = MagicMock()
        agent_fn = langgraph_adapter(model=mock_model)

        assert callable(agent_fn)

    def test_agent_fn_calls_langgraph(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_model = MagicMock()

        # Mock the compiled graph returned by create_react_agent
        mock_compiled = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "The answer is 42."
        mock_compiled.invoke.return_value = {"messages": [mock_message]}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(model=mock_model, system_prompt="Be helpful.")
        tools = [_make_tool_spec()]

        result = agent_fn("What is 6*7?", tools)

        # create_react_agent was called
        mock_langgraph.assert_called_once()
        args, kwargs = mock_langgraph.call_args
        assert args[0] is mock_model  # model is first positional arg
        assert len(args[1]) == 1  # tools is second positional arg
        assert kwargs.get("state_modifier") == "Be helpful."

        # graph.invoke was called with the task
        mock_compiled.invoke.assert_called_once_with(
            {"messages": [("user", "What is 6*7?")]}
        )
        assert result == "The answer is 42."

    def test_result_converted_to_string(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_model = MagicMock()
        mock_compiled = MagicMock()
        mock_message = MagicMock()
        mock_message.content = 42  # non-string
        mock_compiled.invoke.return_value = {"messages": [mock_message]}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(model=mock_model)
        result = agent_fn("task", [])

        assert result == "42"
        assert isinstance(result, str)

    def test_empty_messages_returns_result_string(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_model = MagicMock()
        mock_compiled = MagicMock()
        mock_compiled.invoke.return_value = {"messages": []}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(model=mock_model)
        result = agent_fn("task", [])

        # Falls back to str(result)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Tests: langgraph_adapter with existing graph
# ---------------------------------------------------------------------------

class TestLangGraphAdapterWithGraph:
    def test_uses_graph_model(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_graph = MagicMock()
        mock_graph.model = MagicMock()
        mock_graph.tools = []

        mock_compiled = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "done"
        mock_compiled.invoke.return_value = {"messages": [mock_message]}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(mock_graph)
        arise_tools = [_make_tool_spec()]

        result = agent_fn("do something", arise_tools)

        args, kwargs = mock_langgraph.call_args
        assert args[0] is mock_graph.model
        # Should have 1 ARISE tool
        assert len(args[1]) == 1
        assert result == "done"

    def test_merges_existing_tools(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        existing_tool = MagicMock()
        mock_graph = MagicMock()
        mock_graph.model = MagicMock()
        mock_graph.tools = [existing_tool]

        mock_compiled = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "merged"
        mock_compiled.invoke.return_value = {"messages": [mock_message]}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(mock_graph)
        arise_tools = [_make_tool_spec()]

        result = agent_fn("do something", arise_tools)

        args, _ = mock_langgraph.call_args
        # existing_tool + 1 ARISE tool = 2
        assert len(args[1]) == 2

    def test_positional_graph_argument(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_graph = MagicMock()
        mock_graph.model = MagicMock()
        mock_graph.tools = []

        mock_compiled = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "positional works"
        mock_compiled.invoke.return_value = {"messages": [mock_message]}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(mock_graph)
        result = agent_fn("task", [])

        assert result == "positional works"

    def test_works_with_no_existing_tools(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_graph = MagicMock()
        mock_graph.model = MagicMock()
        mock_graph.tools = None

        mock_compiled = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "ok"
        mock_compiled.invoke.return_value = {"messages": [mock_message]}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(graph=mock_graph)
        result = agent_fn("task", [_make_tool_spec()])

        args, _ = mock_langgraph.call_args
        assert len(args[1]) == 1


# ---------------------------------------------------------------------------
# Tests: validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_raises_if_no_graph_or_model(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        with pytest.raises(ValueError, match="Either 'graph'.*or 'model'"):
            langgraph_adapter()

    def test_import_error_without_langgraph(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "langgraph", raising=False)
        monkeypatch.delitem(sys.modules, "langgraph.prebuilt", raising=False)
        monkeypatch.delitem(sys.modules, "langchain_core", raising=False)
        monkeypatch.delitem(sys.modules, "langchain_core.tools", raising=False)
        monkeypatch.delitem(sys.modules, "arise.adapters.langgraph", raising=False)

        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def mock_import(name, *args, **kwargs):
            if name == "langgraph" or name.startswith("langgraph."):
                raise ImportError("No module named 'langgraph'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        import importlib
        mod = importlib.import_module("arise.adapters.langgraph")
        importlib.reload(mod)

        with pytest.raises(ImportError, match="langgraph"):
            mod._check_langgraph_installed()


# ---------------------------------------------------------------------------
# Tests: multiple tools
# ---------------------------------------------------------------------------

class TestMultipleTools:
    def test_multiple_arise_tools_converted(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_model = MagicMock()
        mock_compiled = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "result"
        mock_compiled.invoke.return_value = {"messages": [mock_message]}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(model=mock_model)
        tools = [
            _make_tool_spec(name="tool_a", description="Tool A"),
            _make_tool_spec(name="tool_b", description="Tool B"),
            _make_tool_spec_with_default(),
        ]

        result = agent_fn("use all tools", tools)

        args, _ = mock_langgraph.call_args
        assert len(args[1]) == 3
        assert result == "result"


# ---------------------------------------------------------------------------
# Tests: message content extraction
# ---------------------------------------------------------------------------

class TestMessageExtraction:
    def test_extracts_content_from_last_message(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_model = MagicMock()
        mock_compiled = MagicMock()

        msg1 = MagicMock()
        msg1.content = "intermediate"
        msg2 = MagicMock()
        msg2.content = "final answer"

        mock_compiled.invoke.return_value = {"messages": [msg1, msg2]}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(model=mock_model)
        result = agent_fn("task", [])

        assert result == "final answer"

    def test_handles_message_without_content_attr(self, mock_langgraph):
        from arise.adapters.langgraph import langgraph_adapter

        mock_model = MagicMock()
        mock_compiled = MagicMock()
        mock_compiled.invoke.return_value = {"messages": ["plain string message"]}
        mock_langgraph.return_value = mock_compiled

        agent_fn = langgraph_adapter(model=mock_model)
        result = agent_fn("task", [])

        assert result == "plain string message"
