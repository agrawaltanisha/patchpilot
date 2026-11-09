"""
Steps 6 & 8: Run existing tests (baseline) and re-run after patching.

V1 supports pytest-based Python repos only, as scoped. Shells out to
`python -m pytest` so it works with whatever interpreter/venv the repo
already expects, and parses the standard summary line pytest prints,
e.g. "2 passed, 1 failed in 0.12s".
"""
import re
import subprocess
from dataclasses import dataclass, field

import config


@dataclass
class TestResult:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    returncode: int = 1
    raw_output: str = ""
    timed_out: bool = False

    @property
    def all_passed(self) -> bool:
        return self.returncode == 0 and self.failed == 0 and self.errors == 0

    @property
    def summary(self) -> str:
        if self.timed_out:
            return "TIMED OUT"
        return f"{self.passed} passed, {self.failed} failed, {self.errors} errors"


def _parse_summary(output: str) -> tuple:
    # pytest's final summary line looks like:
    # "===== 1 failed, 2 passed in 0.03s ====="
    # We search the last ~5 lines for the numbers, defaulting to 0.
    tail = "\n".join(output.strip().splitlines()[-6:])
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", tail)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", tail)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", tail)) else 0
    return passed, failed, errors


def run_tests(repo_path: str, test_paths: list = None) -> TestResult:
    """Runs pytest inside repo_path. If test_paths is given, only those
    files/dirs are run (relative to repo_path); otherwise the whole repo
    is discovered by pytest itself."""
    cmd = ["python3", "-m", "pytest", "-q", "--no-header"]
    if test_paths:
        cmd.extend(test_paths)

    try:
        result = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True,
            timeout=config.TEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        return TestResult(
            raw_output=(e.stdout or "") + (e.stderr or ""),
            timed_out=True, returncode=1,
        )

    output = result.stdout + "\n" + result.stderr
    passed, failed, errors = _parse_summary(output)

    return TestResult(
        passed=passed, failed=failed, errors=errors,
        returncode=result.returncode, raw_output=output,
    )
