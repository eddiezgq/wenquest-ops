"""Process flow chart rules, step 22d (ADR-0022). Pure functions: no database, no AI, no network.

The shape of steps, branches and links; what stops approval (a branch to a step that is gone, a link to nothing in
effect); which operations no PFMEA row analyses yet (shown, not blocking); and the fingerprint of what was approved.
"""

from __future__ import annotations

import hashlib
import json
import re

from wqops.i18n import say

KINDS = {"operation": "Operation", "inspection": "Inspection", "move": "Move", "store": "Storage", "delay": "Wait"}
BRANCH_KINDS = ("rework", "scrap", "other")
LINK_KINDS = {"documents": "Document", "fmea": "PFMEA row", "plan": "Incoming inspection plan",
              "template": "Production template", "gauges": "Measuring equipment"}
MAX_LIST = 12
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class FlowRuleError(ValueError):
    pass


def kinds() -> dict[str, str]:
    """The kinds of step in the reader's language (the keys are what is stored)."""
    return {"operation": say("flow kind::Operation"), "inspection": say("Inspection"), "move": say("Move"),
            "store": say("Storage"), "delay": say("Wait")}


def _key(v, what: str, n: int = 60) -> str:
    s = CONTROL.sub("", str(v if v is not None else "")).strip()[:n]
    if not s:
        raise FlowRuleError(say("{what} is empty", what=what))
    return s


def branches(v, seqs: set[int], own: int | None) -> list[dict]:
    """[{to, label, kind}]: each to another step of the chart, or (to: null) out of the flow for scrap or other, such
    as a lot returned to the supplier."""
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        raise FlowRuleError(say("branches are a list"))
    out = []
    for b in v[:MAX_LIST]:
        if not isinstance(b, dict):
            raise FlowRuleError(say("a branch has a step to go to and a label"))
        to = b.get("to")
        kind = b.get("kind") or "other"
        if kind not in BRANCH_KINDS:
            raise FlowRuleError(say("a branch is rework, scrap or other"))
        if to is None and kind != "rework":
            pass                                   # leaves the flow: scrapped, returned to the supplier
        elif type(to) is not int or to not in seqs:
            raise FlowRuleError(say("a branch goes to a step of this chart (a rework branch always does)"))
        elif to == own:
            raise FlowRuleError(say("a branch goes to another step"))
        out.append({"to": to, "label": CONTROL.sub(" ", str(b.get("label") or "")).strip()[:80], "kind": kind})
    return out


def links(v) -> dict:  # noqa: PLR0912 - one block per kind of link
    """{documents: [number], fmea: [{name, seq}], plan: item, template: code, gauges: [code]}; empty parts left out."""
    if v in (None, ""):
        return {}
    if not isinstance(v, dict):
        raise FlowRuleError(say("links are an object"))
    bad = set(v) - set(LINK_KINDS)
    if bad:
        raise FlowRuleError(say("{bad} is not something a step links to", bad=sorted(bad)[0]))
    out: dict = {}
    for k in ("documents", "gauges"):
        items = v.get(k) or []
        if not isinstance(items, list):
            raise FlowRuleError(say("{k} is a list", k=k))
        keys = []
        what = say("a document number") if k == "documents" else say("a measuring equipment number")
        for x in items[:MAX_LIST]:
            s = _key(x, what)
            if s not in keys:
                keys.append(s)
        if keys:
            out[k] = keys
    fm = v.get("fmea") or []
    if not isinstance(fm, list):
        raise FlowRuleError(say("fmea is a list of PFMEA rows"))
    rows = []
    for x in fm[:MAX_LIST]:
        if not isinstance(x, dict) or type(x.get("seq")) is not int:
            raise FlowRuleError(say("a PFMEA row is its PFMEA number and its row number"))
        r = {"name": _key(x.get("name"), say("the PFMEA number")), "seq": x["seq"]}
        if r not in rows:
            rows.append(r)
    if rows:
        out["fmea"] = rows
    for k in ("plan", "template"):
        if v.get(k) not in (None, ""):
            out[k] = _key(v[k], say("incoming inspection plan") if k == "plan" else say("production template"), 140)
    return out


def link_keys(lk: dict) -> list[tuple[str, str]]:
    """(kind, key) for every link of a step, in a fixed order."""
    out = [("documents", d) for d in lk.get("documents", [])]
    out += [("fmea", f"{r['name']}#{r['seq']}") for r in lk.get("fmea", [])]
    out += [(k, lk[k]) for k in ("plan", "template") if lk.get(k)]
    out += [("gauges", g) for g in lk.get("gauges", [])]
    return out


def _unresolved(step: str, kind: str, key: str, why: str) -> str:
    """One link that points to nothing in effect, as a whole sentence per kind of link."""
    if kind == "documents":
        return say("step {step}: document {key}: {why}", step=step, key=key, why=why)
    if kind == "fmea":
        name, _, seq = key.rpartition("#")
        return say("step {step}: pfmea row {name} row {seq}: {why}", step=step, name=name, seq=seq, why=why)
    if kind == "plan":
        return say("step {step}: incoming inspection plan {key}: {why}", step=step, key=key, why=why)
    if kind == "template":
        return say("step {step}: production template {key}: {why}", step=step, key=key, why=why)
    return say("step {step}: measuring equipment {key}: {why}", step=step, key=key, why=why)


def to_approve(chart: dict, steps: list[dict], resolved: dict[str, dict]) -> list[str]:
    """What still stands between the draft and approval. ``resolved`` maps "kind:key" to what the link points to
    now ({ok, why})."""
    out = []
    if not steps:
        out.append(say("at least one step"))
    seqs = {s["seq"] for s in steps}
    for s in steps:
        n = f"{s['code'] or s['seq']} {s['name']}"
        for b in s.get("branches") or []:
            if b["to"] is not None and b["to"] not in seqs:
                out.append(say("step {step}: a branch goes to a step that was removed", step=n))
        for kind, key in link_keys(s.get("links") or {}):
            r = resolved.get(f"{kind}:{key}") or {"ok": False, "why": say("not checked")}
            if not r["ok"]:
                out.append(_unresolved(n, kind, key, r["why"]))
    return out


def not_analysed(steps: list[dict]) -> list[str]:
    """Operations and inspections no PFMEA row is linked to yet (a note for the team, not a block)."""
    return [f"{s['code'] or s['seq']} {s['name']}" for s in steps
            if s["kind"] in ("operation", "inspection") and not (s.get("links") or {}).get("fmea")]


STEP_KEYS = ("seq", "code", "kind", "name", "description", "branches", "links")
CHART_KEYS = ("name", "version", "title", "item_code", "scope", "owner")


def fingerprint(chart: dict, steps: list[dict], resolved: dict) -> str:
    body = {"chart": {k: chart.get(k) for k in CHART_KEYS},
            "steps": [{k: s.get(k) for k in STEP_KEYS} for s in sorted(steps, key=lambda x: x["seq"])],
            "resolved": resolved}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
