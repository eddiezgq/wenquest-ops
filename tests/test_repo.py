"""Repository conventions (docs/plan.md, CLAUDE.md)."""

import re
from pathlib import Path

import wqops

ROOT = Path(__file__).resolve().parents[1]


def test_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", wqops.__version__)


def test_adrs_are_numbered_and_have_status():
    adrs = sorted((ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    assert adrs, "docs/adr should hold the decisions"
    numbers = [int(p.name[:4]) for p in adrs]
    assert numbers == list(range(1, len(adrs) + 1)), "ADR numbers run 0001, 0002, ... without gaps"
    for p in adrs:
        text = p.read_text(encoding="utf-8")
        assert text.startswith(f"# ADR-{p.name[:4]}"), p.name
        assert "- 状态：" in text, f"{p.name} needs a status line"


def test_plan_lists_phase_one_tasks():
    plan = (ROOT / "docs" / "plan.md").read_text(encoding="utf-8")
    section = plan.split("## 第 1 期分项任务")[1].split("\n## ")[0]          # up to the next section
    rows = re.findall(r"^\| (\d+) \|", section, flags=re.M)
    assert rows == [str(i) for i in range(1, 12)]   # item 11 (ADR-0013) added after acceptance


def test_no_secrets_committed():
    pattern = re.compile(r"(sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16})")
    suffixes = {".py", ".md", ".yml", ".yaml", ".toml", ".json", ".sh"}
    for p in ROOT.rglob("*"):
        if p.is_file() and not {".git", "node_modules", ".venv"} & set(p.parts) and p.suffix in suffixes:
            assert not pattern.search(p.read_text(encoding="utf-8", errors="ignore")), p
