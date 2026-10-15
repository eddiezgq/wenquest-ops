"""Judgement and record code must not use AI or the network (ADR-0010, after dee-qms gate-isolation).

Module-level check of direct imports: quality records, automatic NCRs, supplier facts, SPC, metrics, anomaly rules,
root causes, incoming inspection and sampling (17b), and the document library's records, quote check, text extraction
and file store decide or record things; the AI layer and network libraries stay out of them.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "wqops"
DECISION = ["hub/quality/records.py", "hub/quality/auto.py", "hub/quality/incoming.py", "hub/quality/spc.py",
            "hub/ont/metrics.py", "hub/ont/anomaly.py", "hub/ont/chain.py",
            "hub/docs/library.py", "hub/docs/classify.py", "hub/docs/extract.py", "hub/docs/store.py",
            "hub/docs/checks.py", "hub/docs/ledger.py", "hub/docs/ledgers.py", "hub/quality/workflow.py",
            "hub/quality/workflow_admin.py", "hub/quality/workflow_proposals.py",
            "hub/system/rules.py", "hub/system/qms.py", "hub/system/registers.py", "hub/system/gaps.py",
            "hub/system/setup.py", "hub/quality/sampling.py", "hub/quality/iqc.py",
            "hub/quality/approval.py", "hub/quality/asl.py", "hub/docs/control.py",
            "hub/quality/complaint_rules.py", "hub/quality/complaints.py",
            "hub/quality/cal_rules.py", "hub/quality/calibration.py",
            "hub/quality/change_rules.py", "hub/quality/change_control.py"]
FORBIDDEN = {"openai", "anthropic", "requests", "httpx", "urllib", "urllib3", "aiohttp", "socket", "http",
             "langchain", "litellm", "boto3"}


def imports(path: Path) -> list[tuple[int, str]]:
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out += [(node.lineno, f"{node.module}.{a.name}") for a in node.names]
    return out


def test_decision_modules_use_no_ai_or_network():
    bad = []
    for rel in DECISION:
        for line, name in imports(ROOT / rel):
            if name.startswith("wqops.hub.ai") or name.split(".")[0] in FORBIDDEN or name.startswith("wqops.erp."):
                bad.append(f"{rel}:{line} imports {name}")
    assert bad == []


def test_the_check_catches_offenders(tmp_path):
    p = tmp_path / "x.py"
    p.write_text("import httpx\nfrom wqops.hub.ai import agent\nfrom wqops.hub.ont import metrics\n")
    names = [n for _, n in imports(p)]
    assert names == ["httpx", "wqops.hub.ai.agent", "wqops.hub.ont.metrics"]
