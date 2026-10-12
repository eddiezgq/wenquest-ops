"""GitHub Actions workflows are valid (a broken workflow silently runs nothing)."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_actionlint():
    exe = shutil.which("actionlint")
    if exe is None:
        pytest.fail("actionlint is missing: pip install -e '.[dev]'")
    files = sorted(str(p) for p in (ROOT / ".github" / "workflows").glob("*.yml"))
    r = subprocess.run([exe, *files], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
