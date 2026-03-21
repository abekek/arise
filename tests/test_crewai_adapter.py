"""Tests for the CrewAI adapter.

All tests mock the crewai package so they run without crewai installed.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from arise.types import ToolSpec


# ---------------------------------------------------------------------------
# Fixtures: mock the entire crewai package before importing the adapter
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_crewai(monkeypatch):
    """Inject a mock crewai package into sys.modules so the adapter can import it."""
    crewai_mod = types.ModuleType("crewai")
    crewai_tools_mod = types.ModuleType("crewai.tools")

    # crewai.tools.tool: a decorator that just returns the function as-is
    def fake_tool_decorator(fn):
        fn._is_crewai_tool = True
        return fn

    crewai_tools_mod.tool = fake_tool_decorator

    crewai_mod.tools = crewai_tools_mod

    monkeypatch.setitem(sys.modules, "crewai", crewai_mod)
    monkeypatch.setitem(sys.modules, "crewai.tools", crewai_tools_mod)


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
# Tests: _toolspec_to_crewai_tool
# ---------------------------------------------------------------------------

class TestToolSpecConversion:
    def test_basic_conversion(self):
        from arise.adapters.crewai import _toolspec_to_crewai_tool

        ts = _make_tool_spec()
        crewai_tool = _toolspec_to_crewai_tool(ts)

        assert callable(crewai_tool)
        assert crewai_tool.__name__ == "greet"
        assert crewai_tool.__doc__ == "Say hello"
        assert hasattr(crewai_tool, "_is_crewai_tool")

    def test_preserves_annotations(self):
        from arise.adapters.crewai import _toolspec_to_crewai_tool

        ts = _make_tool_spec()
        crewai_tool = _toolspec_to_crewai_tool(ts)

        assert crewai_tool.__annotations__["name"] is str
        assert crewai_tool.__annotations__["return"] is str

    def test_tool_is_callable(self):
        from arise.adapters.crewai import _toolspec_to_crewai_tool

        ts = _make_tool_spec()
        crewai_tool = _toolspec_to_crewai_tool(ts)

        result = crewai_tool(name="World")
        assert result == "Hello, World!"

    def test_tool_with_defaults(self):
        from arise.adapters.crewai import _toolspec_to_crewai_tool

        ts = _make_tool_spec_with_default()
        crewai_tool = _toolspec_to_crewai_tool(ts)

        assert crewai_tool(a=3) == 3
        assert crewai_tool(a=3, b=7) == 10

    def test_annotations_for_numeric_types(self):
        from arise.adapters.crewai import _toolspec_to_crewai_tool

        ts = _make_tool_spec_with_default()
        crewai_tool = _toolspec_to_crewai_tool(ts)

        assert crewai_tool.__annotations__["a"] is int
        assert crewai_tool.__annotations__["b"] is int

    def test_hyphenated_name_sanitized(self):
        from arise.adapters.crewai import _toolspec_to_crewai_tool

        ts = _make_tool_spec(name="my-tool", description="A tool with hyphens")
        crewai_tool = _toolspec_to_crewai_tool(ts)

        assert crewai_tool.__name__ == "my_tool"


# ---------------------------------------------------------------------------
# Tests: crewai_adapter
# ---------------------------------------------------------------------------

class TestCrewAIAdapter:
    def test_creates_agent_fn(self):
        from arise.adapters.crewai import crewai_adapter

        mock_crew = MagicMock()
        agent_fn = crewai_adapter(mock_crew)

        assert callable(agent_fn)

    def test_agent_fn_calls_crew_kickoff(self):
        from arise.adapters.crewai import crewai_adapter

        mock_agent = MagicMock()
        mock_agent.tools = []

        mock_crew = MagicMock()
        mock_crew.agents = [mock_agent]
        mock_crew.kickoff.return_value = "The answer is 42."

        agent_fn = crewai_adapter(mock_crew)
        tools = [_make_tool_spec()]

        result = agent_fn("What is 6*7?", tools)

        mock_crew.kickoff.assert_called_once_with(inputs={"task": "What is 6*7?"})
        assert result == "The answer is 42."

    def test_result_converted_to_string(self):
        from arise.adapters.crewai import crewai_adapter

        mock_agent = MagicMock()
        mock_agent.tools = []

        mock_crew = MagicMock()
        mock_crew.agents = [mock_agent]
        mock_crew.kickoff.return_value = 42

        agent_fn = crewai_adapter(mock_crew)
        result = agent_fn("task", [])

        assert result == "42"
        assert isinstance(result, str)

    def test_custom_task_template(self):
        from arise.adapters.crewai import crewai_adapter

        mock_agent = MagicMock()
        mock_agent.tools = []

        mock_crew = MagicMock()
        mock_crew.agents = [mock_agent]
        mock_crew.kickoff.return_value = "done"

        agent_fn = crewai_adapter(mock_crew, task_template="prompt")
        agent_fn("do something", [])

        mock_crew.kickoff.assert_called_once_with(inputs={"prompt": "do something"})

    def test_tools_injected_into_agents(self):
        from arise.adapters.crewai import crewai_adapter

        existing_tool = MagicMock()
        mock_agent = MagicMock()
        mock_agent.tools = [existing_tool]

        mock_crew = MagicMock()
        mock_crew.agents = [mock_agent]
        mock_crew.kickoff.return_value = "done"

        agent_fn = crewai_adapter(mock_crew)
        arise_tools = [_make_tool_spec()]

        agent_fn("task", arise_tools)

        # During kickoff, agent should have had existing + ARISE tools
        # After cleanup, only existing tool should remain
        assert existing_tool in mock_agent.tools
        assert len(mock_agent.tools) == 1

    def test_tools_cleaned_up_after_kickoff(self):
        from arise.adapters.crewai import crewai_adapter

        mock_agent = MagicMock()
        mock_agent.tools = []

        mock_crew = MagicMock()
        mock_crew.agents = [mock_agent]
        mock_crew.kickoff.return_value = "done"

        agent_fn = crewai_adapter(mock_crew)
        agent_fn("task", [_make_tool_spec()])

        # After cleanup, no ARISE tools should remain
        assert len(mock_agent.tools) == 0

    def test_tools_cleaned_up_on_error(self):
        from arise.adapters.crewai import crewai_adapter

        mock_agent = MagicMock()
        mock_agent.tools = []

        mock_crew = MagicMock()
        mock_crew.agents = [mock_agent]
        mock_crew.kickoff.side_effect = RuntimeError("Crew failed")

        agent_fn = crewai_adapter(mock_crew)

        with pytest.raises(RuntimeError, match="Crew failed"):
            agent_fn("task", [_make_tool_spec()])

        # Tools should still be cleaned up even after error
        assert len(mock_agent.tools) == 0

    def test_multiple_tools_converted(self):
        from arise.adapters.crewai import crewai_adapter

        mock_agent = MagicMock()
        mock_agent.tools = []

        mock_crew = MagicMock()
        mock_crew.agents = [mock_agent]
        mock_crew.kickoff.return_value = "result"

        agent_fn = crewai_adapter(mock_crew)
        tools = [
            _make_tool_spec(name="tool_a", description="Tool A"),
            _make_tool_spec(name="tool_b", description="Tool B"),
            _make_tool_spec_with_default(),
        ]

        result = agent_fn("use all tools", tools)
        assert result == "result"

    def test_multiple_agents_get_tools(self):
        from arise.adapters.crewai import crewai_adapter

        mock_agent_1 = MagicMock()
        mock_agent_1.tools = []
        mock_agent_2 = MagicMock()
        mock_agent_2.tools = []

        mock_crew = MagicMock()
        mock_crew.agents = [mock_agent_1, mock_agent_2]
        mock_crew.kickoff.return_value = "done"

        agent_fn = crewai_adapter(mock_crew)
        agent_fn("task", [_make_tool_spec()])

        # Both agents should have been cleaned up
        assert len(mock_agent_1.tools) == 0
        assert len(mock_agent_2.tools) == 0


# ---------------------------------------------------------------------------
# Tests: validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_import_error_without_crewai(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "crewai", raising=False)
        monkeypatch.delitem(sys.modules, "crewai.tools", raising=False)
        monkeypatch.delitem(sys.modules, "arise.adapters.crewai", raising=False)

        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def mock_import(name, *args, **kwargs):
            if name == "crewai" or name.startswith("crewai."):
                raise ImportError("No module named 'crewai'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        import importlib
        mod = importlib.import_module("arise.adapters.crewai")
        importlib.reload(mod)

        with pytest.raises(ImportError, match="crewai"):
            mod._check_crewai_installed()
