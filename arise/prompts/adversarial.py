ADVERSARIAL_TEST_PROMPT = """\
You are a QA engineer trying to break this Python function. Your goal is to find bugs.

FUNCTION NAME: {name}
DESCRIPTION: {description}

IMPLEMENTATION:
```python
{implementation}
```

THE FOLLOWING TESTS ALREADY PASS:
```python
{existing_tests}
```

Generate 3 test cases that are LIKELY TO EXPOSE BUGS. Focus on:
- Edge cases the developer probably didn't think of (empty inputs, None, huge values)
- Type boundary cases
- Off-by-one errors
- Division by zero, empty collections, single-element inputs
- Property checks (if it claims to return a list, assert isinstance(result, list))

Each test must be a function named test_adversarial_*. Use assert statements.
Return ONLY Python test code, no markdown fences.
"""
