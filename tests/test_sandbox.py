import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise.types import Skill
from arise.skills.sandbox import Sandbox


def test_passing_skill():
    sandbox = Sandbox(timeout=10)
    skill = Skill(
        name="add",
        implementation="def add(a, b):\n    return a + b",
        test_suite="def test_add_basic():\n    assert add(1, 2) == 3\n\ndef test_add_negative():\n    assert add(-1, 1) == 0",
    )
    result = sandbox.test_skill(skill)
    assert result.success
    assert result.total_passed == 2
    assert result.total_failed == 0


def test_failing_skill():
    sandbox = Sandbox(timeout=10)
    skill = Skill(
        name="broken",
        implementation="def broken(x):\n    return x + 1",
        test_suite="def test_wrong():\n    assert broken(1) == 3",
    )
    result = sandbox.test_skill(skill)
    assert not result.success
    assert result.total_failed == 1


def test_syntax_error():
    sandbox = Sandbox(timeout=10)
    skill = Skill(
        name="bad",
        implementation="def bad(:\n    pass",
        test_suite="def test_bad():\n    pass",
    )
    result = sandbox.test_skill(skill)
    assert not result.success


def test_timeout():
    sandbox = Sandbox(timeout=2)
    skill = Skill(
        name="slow",
        implementation="import time\ndef slow():\n    time.sleep(10)",
        test_suite="def test_slow():\n    slow()",
    )
    result = sandbox.test_skill(skill)
    assert not result.success


def test_execute_code():
    sandbox = Sandbox(timeout=5)
    stdout, stderr, code = sandbox.execute_code("print('hello')")
    assert "hello" in stdout
    assert code == 0


if __name__ == "__main__":
    test_passing_skill()
    test_failing_skill()
    test_syntax_error()
    test_timeout()
    test_execute_code()
    print("All sandbox tests passed!")
