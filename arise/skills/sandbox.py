from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import time

from arise.types import Skill, SandboxResult, TestResult


class Sandbox:
    def __init__(self, backend: str = "subprocess", timeout: int = 30):
        self.backend = backend
        self.timeout = timeout

    def test_skill(self, skill: Skill) -> SandboxResult:
        if self.backend == "docker":
            return self._test_docker(skill)
        return self._test_subprocess(skill)

    def execute_code(self, code: str, timeout: int | None = None) -> tuple[str, str, int]:
        timeout = timeout or self.timeout
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(code)
            f.flush()
            try:
                result = subprocess.run(
                    ["python", f.name],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                return result.stdout, result.stderr, result.returncode
            except subprocess.TimeoutExpired:
                return "", f"Execution timed out after {timeout}s", 1
            finally:
                os.unlink(f.name)

    def _test_subprocess(self, skill: Skill) -> SandboxResult:
        test_runner = "\n".join([
            "import sys",
            "import time",
            "import json",
            "import traceback",
            "",
            "# --- Skill implementation ---",
            skill.implementation,
            "",
            "# --- Test suite ---",
            "_test_results = []",
            "",
            "def _run_test(test_fn):",
            "    name = test_fn.__name__",
            "    start = time.time()",
            "    try:",
            "        test_fn()",
            "        elapsed = (time.time() - start) * 1000",
            '        _test_results.append({"passed": True, "test_name": name, "error": None, "execution_time_ms": elapsed})',
            "    except Exception as e:",
            "        elapsed = (time.time() - start) * 1000",
            "        tb = traceback.format_exc()",
            '        _test_results.append({"passed": False, "test_name": name, "error": tb, "execution_time_ms": elapsed})',
            "",
            skill.test_suite,
            "",
            "# Discover and run test functions",
            '_test_fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]',
            "for _tf in _test_fns:",
            "    _run_test(_tf)",
            "",
            'print("__ARISE_RESULTS__")',
            "print(json.dumps(_test_results))",
        ])

        stdout, stderr, returncode = self.execute_code(test_runner)

        if "__ARISE_RESULTS__" in stdout:
            parts = stdout.split("__ARISE_RESULTS__")
            pre_output = parts[0]
            raw_json = parts[1].strip()
            try:
                raw_results = __import__("json").loads(raw_json)
                test_results = [TestResult(**r) for r in raw_results]
                passed = sum(1 for t in test_results if t.passed)
                failed = len(test_results) - passed
                return SandboxResult(
                    success=failed == 0,
                    test_results=test_results,
                    total_passed=passed,
                    total_failed=failed,
                    stdout=pre_output,
                    stderr=stderr,
                )
            except Exception:
                pass

        return SandboxResult(
            success=False,
            test_results=[TestResult(passed=False, test_name="__setup__", error=stderr or stdout)],
            total_passed=0,
            total_failed=1,
            stdout=stdout,
            stderr=stderr,
        )

    def _test_docker(self, skill: Skill) -> SandboxResult:
        try:
            import docker as docker_lib
        except ImportError:
            raise RuntimeError("Docker backend requires 'docker' package: pip install arise-ai[docker]")

        client = docker_lib.from_env()

        test_code = (
            skill.implementation
            + "\n\n"
            + skill.test_suite
            + "\n\nimport sys\nfor k,v in dict(globals()).items():\n"
            + "    if k.startswith('test_') and callable(v):\n"
            + "        try:\n            v(); print(f'PASS: {k}')\n"
            + "        except Exception as e:\n            print(f'FAIL: {k}: {e}')\n"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_code)
            tmp_path = f.name

        try:
            container = client.containers.run(
                "python:3.11-slim",
                command=["python", "/tmp/test.py"],
                volumes={tmp_path: {"bind": "/tmp/test.py", "mode": "ro"}},
                network_mode="none",
                mem_limit="256m",
                detach=True,
            )
            container.wait(timeout=self.timeout)
            logs = container.logs().decode()
            container.remove()

            results = []
            for line in logs.strip().split("\n"):
                if line.startswith("PASS:"):
                    results.append(TestResult(passed=True, test_name=line[6:].strip()))
                elif line.startswith("FAIL:"):
                    parts = line[6:].split(":", 1)
                    results.append(TestResult(passed=False, test_name=parts[0].strip(), error=parts[1].strip() if len(parts) > 1 else ""))

            passed = sum(1 for r in results if r.passed)
            return SandboxResult(
                success=all(r.passed for r in results) and len(results) > 0,
                test_results=results,
                total_passed=passed,
                total_failed=len(results) - passed,
                stdout=logs,
                stderr="",
            )
        finally:
            os.unlink(tmp_path)


def _indent(code: str, level: int) -> str:
    return code
