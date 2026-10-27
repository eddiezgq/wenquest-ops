"""Process FMEA rules, step 22c (ADR-0022). Pure functions: no database, no AI, no network.

RPN = S x O x D is computed here, never typed. Whether a row needs action follows the company's own rule: an RPN
threshold (and optionally a severity threshold), or a lookup table of S / O / D ranges giving a priority. A rank
missing, a rank not on the company's scale, no rule, or no table row matching all mean "not determined", which stops
approval: unknown is never a pass. The scales and the rule are the company's; nothing here is a standard's value.
"""

from __future__ import annotations

import hashlib
import json

from wqops.i18n import say

KINDS = ("severity", "occurrence", "detection")
PRIORITIES = ("high", "medium", "low")
RANK_KEYS = {"severity": "severity", "occurrence": "occurrence", "detection": "detection",
             "res_severity": "severity", "res_occurrence": "occurrence", "res_detection": "detection"}


class FmeaRuleError(ValueError):
    pass


def rpn(s: int | None, o: int | None, d: int | None) -> int | None:
    if s is None or o is None or d is None:
        return None
    return s * o * d


def check_rule(cfg: dict) -> dict:
    """The company's rule in a clean shape, or an error saying what is wrong with it."""
    m = cfg.get("method")
    if m == "rpn":
        t = cfg.get("rpn_action")
        if type(t) is not int or not 1 <= t <= 1000:
            raise FmeaRuleError(say("the RPN threshold is a whole number from 1 to 1000"))
        s = cfg.get("severity_action")
        if s not in (None, "") and (type(s) is not int or not 1 <= s <= 10):
            raise FmeaRuleError(say("the severity threshold is a rank from 1 to 10, or empty"))
        return {"method": "rpn", "rpn_action": t, "severity_action": s or None, "rules": [], "needs_action": []}
    if m == "lookup":
        rules = cfg.get("rules")
        if not isinstance(rules, list) or not rules:
            raise FmeaRuleError(say("a lookup rule needs at least one row of ranges"))
        out = []
        for k, r in enumerate(rules, 1):
            if not isinstance(r, dict) or r.get("priority") not in PRIORITIES:
                raise FmeaRuleError(say("row {k}: the priority is high, medium or low", k=k))
            row = {"priority": r["priority"]}
            for key in ("s", "o", "d"):
                lo_hi = r.get(key)
                if (not isinstance(lo_hi, list) or len(lo_hi) != 2 or any(type(x) is not int for x in lo_hi)
                        or not 1 <= lo_hi[0] <= lo_hi[1] <= 10):
                    raise FmeaRuleError(say("row {k}: {key} is a range of ranks, low to high, within 1 to 10",
                                            k=k, key=key.upper()))
                row[key] = list(lo_hi)
            out.append(row)
        need = cfg.get("needs_action") or ["high"]
        if not isinstance(need, list) or any(p not in PRIORITIES for p in need):
            raise FmeaRuleError(say("the priorities that need action are among high, medium and low"))
        return {"method": "lookup", "rpn_action": None, "severity_action": None, "rules": out,
                "needs_action": [p for p in PRIORITIES if p in need]}
    raise FmeaRuleError(say("the rule is an RPN threshold (rpn) or a lookup table (lookup)"))


def judge(cfg: dict | None, s: int | None, o: int | None, d: int | None) -> dict:
    """{rpn, priority, action}: action is True / False, or None when it cannot be determined."""
    n = rpn(s, o, d)
    if cfg is None or n is None:
        return {"rpn": n, "priority": None, "action": None}
    if cfg["method"] == "rpn":
        act = n >= cfg["rpn_action"] or (cfg.get("severity_action") is not None and s >= cfg["severity_action"])
        return {"rpn": n, "priority": "action" if act else "no action", "action": act}
    for r in cfg["rules"]:
        if r["s"][0] <= s <= r["s"][1] and r["o"][0] <= o <= r["o"][1] and r["d"][0] <= d <= r["d"][1]:
            return {"rpn": n, "priority": r["priority"], "action": r["priority"] in cfg["needs_action"]}
    return {"rpn": n, "priority": None, "action": None}


def lookup_gaps(cfg: dict) -> int:
    """How many of the 1000 S / O / D combinations the lookup table leaves undecided (0 for an RPN rule)."""
    if cfg.get("method") != "lookup":
        return 0
    return sum(1 for s in range(1, 11) for o in range(1, 11) for d in range(1, 11)
               if judge(cfg, s, o, d)["priority"] is None)


def row_needs(r: dict, ranks: dict[str, set[int]], cfg: dict | None) -> list[str]:
    """What one row still needs before the PFMEA can be approved."""
    n = f"row {r.get('seq')}"
    out = []
    if not r.get("confirmed", True):
        out.append(f"{n}: drafted by the AI; confirm or remove it")
    for k in ("step", "failure_mode", "effect", "cause"):
        if not (r.get(k) or "").strip():
            out.append(f"{n}: the {k.replace('_', ' ')}")
    for k in ("severity", "occurrence", "detection"):
        v = r.get(k)
        if v is None:
            out.append(f"{n}: the {k} rank")
        elif v not in ranks.get(k, set()):
            out.append(f"{n}: {k} {v} is not on the company's scale")
    if any(r.get(k) is not None for k in ("res_severity", "res_occurrence", "res_detection")):
        for k in ("res_severity", "res_occurrence", "res_detection"):
            v = r.get(k)
            if v is None or v not in ranks.get(RANK_KEYS[k], set()):
                out.append(f"{n}: the ranks after action are given together, on the company's scales")
                break
    j = judge(cfg, r.get("severity"), r.get("occurrence"), r.get("detection"))
    if j["rpn"] is not None and j["action"] is None:
        out.append(f"{n}: the company's rule does not decide whether it needs action")
    if j["action"] and not (r.get("action") or "").strip():
        out.append(f"{n}: needs action under the company's rule: say what is recommended")
    return out


def to_approve(f: dict, rows: list[dict], ranks: dict[str, set[int]], cfg: dict | None) -> list[str]:
    out = []
    if cfg is None:
        out.append("the company's rule for when a row needs action (Process FMEA, criteria)")
    for k in KINDS:
        if not ranks.get(k):
            out.append(f"the company's {k} scale")
    if not rows:
        out.append("at least one failure mode")
    for r in rows:
        out += row_needs(r, ranks, cfg)
    return out


def criteria(scales: list[dict], cfg: dict | None) -> dict:
    return {"scales": sorted(({"kind": x["kind"], "rank": x["rank"], "name": x["name"]} for x in scales
                              if x.get("active", True)), key=lambda x: (x["kind"], x["rank"])),
            "rule": cfg}


ROW_KEYS = ("seq", "step", "requirement", "failure_mode", "effect", "severity", "cause", "occurrence", "prevention",
            "detection_controls", "detection", "action", "action_owner", "action_due", "res_severity",
            "res_occurrence", "res_detection", "refs", "origin", "rpn", "res_rpn", "priority")
FILE_KEYS = ("name", "version", "process", "item_code", "scope", "owner")


def fingerprint(f: dict, rows: list[dict], crit: dict) -> str:
    """SHA-256 of what was approved: the PFMEA, its rows and the criteria used."""
    def val(v):
        return v.isoformat() if hasattr(v, "isoformat") else list(v) if isinstance(v, tuple) else v

    body = {"file": {k: val(f.get(k)) for k in FILE_KEYS},
            "rows": [{k: val(r.get(k)) for k in ROW_KEYS} for r in sorted(rows, key=lambda x: x["seq"])],
            "criteria": crit}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def verify(proposals: list[dict], shown: set[str]) -> tuple[list[dict], list[dict]]:
    """Keep the AI's drafted rows that cite at least one record it was shown (others dropped, with the reason)."""
    kept, dropped = [], []
    for p in proposals:
        refs = [str(x).strip()[:60] for x in (p.get("refs") or []) if str(x).strip()][:8]
        good = [x for x in refs if x in shown]
        if not good:
            dropped.append({"failure_mode": str(p.get("failure_mode") or "")[:200], "refs": refs,
                            "reason": "cites no record it was shown" if refs else "cites no record"})
        else:
            kept.append(p | {"refs": good})
    return kept, dropped
