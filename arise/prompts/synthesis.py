SYNTHESIS_PROMPT = """\
You are creating a Python tool for an AI agent.

REQUIRED CAPABILITY:
{description}

FUNCTION SIGNATURE (suggested):
{signature}

EXISTING TOOLS (for reference — you can call these):
{existing_tools}

EXAMPLES OF TASKS WHERE THIS TOOL WAS NEEDED:
{evidence}

REQUIREMENTS:
1. Write a single Python function
2. Include type hints for all parameters and return value
3. Include a docstring explaining what it does, parameters, and return value
4. Handle errors gracefully — return error info, don't crash
5. Use only standard library + common packages (pandas, numpy, scipy, sklearn)
6. The function must be self-contained (no global state)
7. Keep it focused — one tool, one job

Return ONLY a JSON object with these fields:
{{
    "name": "function_name",
    "description": "One-line description for the agent to understand when to use this",
    "implementation": "full Python function source code",
    "test_suite": "test code with functions named test_* that use assert statements"
}}
"""
