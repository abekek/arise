GAP_DETECTION_PROMPT = """\
You are analyzing failed agent trajectories to identify missing tool capabilities.

The agent has access to these tools:
{existing_tools}

Here are recent failed tasks:
{trajectories}

The agent failed because it lacks the right tools to solve these tasks.
Look at what the TASKS are asking for, not just the error messages.

For each distinct capability gap, suggest a NEW TOOL the agent needs.
Focus on high-level capabilities (e.g., "compute average", "calculate factorial") NOT low-level fixes (e.g., "convert string to int").

Return a JSON array of gaps (max 3):
[
  {{
    "description": "Brief description of the missing capability",
    "evidence": ["Task description that needed this"],
    "suggested_name": "function_name",
    "suggested_signature": "def function_name(param1: type, param2: type) -> return_type",
    "similar_existing": []
  }}
]

Rules:
- Only suggest tools that would directly solve the TASK, not workaround tools
- Don't suggest tools that duplicate existing capabilities
- Return [] if no genuine gaps exist
"""
