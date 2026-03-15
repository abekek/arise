REFINEMENT_PROMPT = """\
You need to fix/improve a Python tool that has issues.

FUNCTION NAME: {name}
DESCRIPTION: {description}

CURRENT IMPLEMENTATION:
```python
{implementation}
```

CURRENT TEST SUITE:
```python
{test_suite}
```

FEEDBACK / ERRORS:
{feedback}

Fix the implementation (and tests if needed) based on the feedback. Keep the same function name and signature if possible.

Return ONLY a JSON object:
{{
    "implementation": "fixed Python function source code",
    "test_suite": "updated test code if needed, or the original test code"
}}
"""
