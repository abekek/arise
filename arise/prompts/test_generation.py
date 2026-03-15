TEST_GENERATION_PROMPT = """\
Generate test cases for the following Python function.

FUNCTION NAME: {name}
DESCRIPTION: {description}

IMPLEMENTATION:
```python
{implementation}
```

Generate {num_tests} test functions. Each test should:
1. Be named test_<descriptive_name>
2. Use assert statements (no pytest fixtures needed)
3. Cover: happy path, edge cases, error handling
4. Be self-contained — no external dependencies

Return ONLY the Python test code (no JSON wrapping, no markdown):
"""
