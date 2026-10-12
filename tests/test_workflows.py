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


@pytest.mark.parametrize(("changed", "expected"), [
    ([".github/scripts/x.py", *[f"tests/t{i}.py" for i in range(20000)]], "true"),  # match first, then > 64 KB
    ([*[f"docs/d{i}.md" for i in range(3000)], "wqops/hub/app.py"], "true"),
    ([f"docs/d{i}.md" for i in range(100)], "false"),
])
def test_ci_scope_decides_from_changed_files(tmp_path, changed, expected):
    """`echo | grep -q` under pipefail fails when grep stops reading early (SIGPIPE) on a large diff."""
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    for f in changed:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "change")
    out = tmp_path / "out"
    head = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    env = {"PATH": "/usr/bin:/bin", "GITHUB_EVENT_NAME": "pull_request", "GITHUB_OUTPUT": str(out),
           "BASE": f"{head}~1", "GITHUB_SHA": head, "LABELS": ""}
    script = Path(__file__).resolve().parents[1] / ".github/scripts/ci_scope.sh"
    for _ in range(5):  # the bug was a race; repeat
        out.write_text("")
        r = subprocess.run(["bash", str(script)], cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stderr
        assert out.read_text().strip() == f"install={expected}"
