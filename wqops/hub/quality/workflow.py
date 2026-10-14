"""Quality workflows as configuration (ADR-0015, step 15a): loading a workflow, checking it against the red lines
of ADR-0010, versions pinned to records, and the guard every step of a record passes before it runs.

A workflow says which states a record has, which steps move it, who may run each step, what each step needs, whether
it is signed and who may not run it. The steps themselves are carried out by quality/records.py; this module decides
whether they may run. Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import yaml
from psycopg.types.json import Json

from wqops.hub import permissions as P

DIR = Path(__file__).resolve().parent / "workflows"
KINDS = {"ncr": "ncr_records", "capa": "capas"}
# the steps quality/records.py carries out; a workflow configures them, it cannot drop them
BUILT_IN = {
    "ncr": {"update", "contain", "disposition", "approve", "reject_disposition", "close", "cancel", "complete_8d"},
    "capa": {"submit", "plan", "to_effectiveness", "not_effective", "effective", "cancel"},
}
# separation of duties in the default workflows: a configuration may add to these, never remove them
NOT_BY = {("ncr", "approve"): {"disposition_by"}, ("capa", "effective"): {"owner"}}
# what a step may need, as the people using it say it
NEEDS = {
    "ncr": {"containment": "containment", "disposition": "disposition", "disposition_qty": "quantity",
            "disposition_reason": "reason"},
    "capa": {"description": "problem description", "owner": "owner", "risk": "risk level",
             "containment": "containment", "root_cause": "root cause", "actions": "at least one action",
             "actions_done": "every action done", "evidence": "evidence"},
}
WHO = {"disposition_by": "the person who submitted the disposition", "owner": "the owner",
       "created_by": "the person who opened it", "submitted_by": "the person who submitted it",
       "confirmed_by": "the person who confirmed it"}
SEVERITIES = ("minor", "major")


class WorkflowError(ValueError):
    """The workflow configuration breaks a rule; nothing was saved."""


class StepError(ValueError):
    """A step may not run now (state, missing field, separation of duties)."""


class NotAllowed(PermissionError):
    pass


def default(kind: str) -> dict:
    return yaml.safe_load((DIR / f"{kind}.yaml").read_text(encoding="utf-8"))


def fingerprint(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------- red lines

def validate(cfg: dict, in_use: set[str] | None = None) -> list[str]:  # noqa: PLR0912, PLR0915
    """Everything wrong with a workflow, in plain words; empty when it may be saved. ``in_use``: states that records
    are in now (a new version cannot drop them)."""
    errs: list[str] = []
    kind = cfg.get("kind")
    if kind not in KINDS:
        return [f"kind must be one of: {', '.join(KINDS)}"]
    states, steps = cfg.get("states") or {}, cfg.get("steps") or {}
    if cfg.get("initial") not in states:
        errs.append("the first state (initial) must be one of the states")
    finals = {s for s, v in states.items() if (v or {}).get("final")}
    if not finals:
        errs.append("there must be at least one final state")
    num = cfg.get("numbering") or {}
    if not str(num.get("prefix") or "").replace("-", "").isalnum() or not 3 <= int(num.get("digits") or 0) <= 8:
        errs.append("numbering needs a prefix of letters or digits and 3 to 8 digits")
    for name in sorted(BUILT_IN[kind] - set(steps)):
        errs.append(f"step {name} is carried out by WenQuest Ops and cannot be removed")
    for name, raw in steps.items():
        st = raw or {}
        if name not in BUILT_IN[kind]:
            errs.append(f"step {name} is not a step WenQuest Ops can carry out")
            continue
        for s in [*(st.get("from") or []), *(x for x in (st.get("to"), st.get("to_when_approval_needed")) if x)]:
            if s not in states:
                errs.append(f"step {name}: state {s} does not exist")
        if not st.get("from"):
            errs.append(f"step {name}: say from which states it runs")
        if any(s in finals for s in st.get("from") or []):
            errs.append(f"step {name}: a final state is locked; no step may start from it")
        if st.get("permission") not in P.PERMISSIONS:
            errs.append(f"step {name}: permission {st.get('permission')!r} does not exist")
        if st.get("kind") in ("approval", "close") and not str(st.get("sign") or "").strip():
            errs.append(f"step {name}: approving and closing are signed with the person's password")
        missing_sep = NOT_BY.get((kind, name), set()) - set(st.get("not_by") or [])
        if missing_sep:
            errs.append(f"step {name}: {', '.join(WHO.get(x, x) for x in sorted(missing_sep))} may not do it; this "
                        "separation of duties cannot be removed")
        for x in st.get("not_by") or []:
            if x not in WHO:
                errs.append(f"step {name}: unknown person {x!r} in not_by")
        for f in st.get("required") or []:
            if f not in NEEDS[kind]:
                errs.append(f"step {name}: unknown field {f!r} in required")
        for r in st.get("roles") or []:
            if r not in P.ROLE_PERMISSIONS:
                errs.append(f"step {name}: unknown role {r!r}")
    for name in BUILT_IN[kind] & set(steps):
        want = default(kind)["steps"][name].get("kind")
        if want and (steps[name] or {}).get("kind") != want:
            errs.append(f"step {name} stays a {want} step (signed)")
    # every state reachable, every open state has a way out
    if cfg.get("initial") in states:
        seen, todo = set(), [cfg["initial"]]
        while todo:
            s = todo.pop()
            if s in seen:
                continue
            seen.add(s)
            for st in steps.values():
                if s in ((st or {}).get("from") or []):
                    todo += [x for x in ((st or {}).get("to"), (st or {}).get("to_when_approval_needed")) if x]
        for s in sorted(set(states) - seen):
            errs.append(f"state {s} cannot be reached")
        for s in sorted(set(states) - finals):
            if not any(s in ((st or {}).get("from") or []) and (st or {}).get("to") not in (None, s)
                       for st in steps.values()):
                errs.append(f"state {s} has no step out of it; records would be stuck")
    for s in sorted((in_use or set()) - set(states)):
        errs.append(f"records are in state {s} now; a new version cannot remove it")
    rules = cfg.get("rules") or {}
    for key in ("capa_closed_before_close", "eight_d_before_close"):
        if kind == "ncr" and any(x not in SEVERITIES for x in rules.get(key) or []):
            errs.append(f"rule {key}: severities are {', '.join(SEVERITIES)}")
    if kind == "ncr" and "major" not in (rules.get("capa_closed_before_close") or []):
        errs.append("a major nonconformance closes only after its corrective action is closed; this cannot be removed")
    if kind == "capa" and rules.get("one_open_capa_per_ncr") is not True:
        errs.append("one open corrective action per nonconformance report cannot be removed")
    return list(dict.fromkeys(errs))


# ---------------------------------------------------------------- versions

def ensure(conn, kind: str) -> dict:
    """The enabled version of a workflow; the default becomes version 1 the first time it is needed."""
    row = conn.execute("select * from workflow_versions where kind = %s and status = 'enabled' order by version desc "
                       "limit 1", (kind,)).fetchone()
    if row:
        return row
    cfg = default(kind)
    bad = validate(cfg)
    if bad:
        raise WorkflowError(f"the default {kind} workflow is wrong: {'; '.join(bad)}")
    conn.execute("insert into workflow_versions (kind, version, config, status, fingerprint, created_by, enabled_by, "
                 "enabled_at, note) values (%s, 1, %s, 'enabled', %s, 'WenQuest Ops', 'WenQuest Ops', now(), "
                 "'default workflow') on conflict (kind, version) do nothing", (kind, Json(cfg), fingerprint(cfg)))
    return conn.execute("select * from workflow_versions where kind = %s and status = 'enabled' order by version desc "
                        "limit 1", (kind,)).fetchone()


def version(conn, kind: str, vid: int | None) -> dict:
    """The version a record was started under (records from before versions use the current one)."""
    if vid:
        row = conn.execute("select * from workflow_versions where id = %s", (vid,)).fetchone()
        if row:
            return row
    return ensure(conn, kind)


def of(conn, kind: str, record: dict | None = None) -> dict:
    return version(conn, kind, (record or {}).get("workflow_version"))["config"]


# ---------------------------------------------------------------- the guard

def _label(cfg: dict, state: str) -> str:
    return state.replace("_", " ")


def check(cfg: dict, record: dict, step: str, user: dict | None, facts: dict | None = None,
          *, name_field: str = "name", explain: dict | None = None) -> dict:
    """May ``user`` run ``step`` on ``record`` now? Raises StepError or NotAllowed with what is wrong; returns the
    step's configuration. ``facts``: values the step brings or computes (fields typed in, actions done, ...);
    ``explain``: a fuller message for a missing field. The signature itself is checked by the caller, before its
    transaction (records.check_signer)."""
    st = cfg["steps"].get(step)
    if st is None:
        raise StepError(f"this workflow has no step {step}")
    if record["status"] not in st["from"]:
        raise StepError(f"{record[name_field]} is {_label(cfg, record['status'])}; this step needs it to be "
                        f"{' or '.join(_label(cfg, s) for s in st['from'])}")
    if user is not None:
        roles = user.get("roles") or []
        if roles and st.get("permission") and not P.allows(roles, st["permission"]):
            raise NotAllowed(f"your role does not allow: {P.PERMISSIONS[st['permission']]}")
        if st.get("roles") and roles and not set(roles) & set(st["roles"]):
            raise NotAllowed(f"{st.get('label', step)}: only {', '.join(st['roles'])} may do this")
        for f in st.get("not_by") or []:
            if record.get(f) and record.get(f) == user.get("email"):
                raise StepError(f"someone other than {WHO.get(f, f)} must do this ({st.get('label', step).lower()})")
    values = {**record, **(facts or {})}
    gaps = [f for f in st.get("required") or [] if values.get(f) in (None, "", [], False, 0)]
    for f in gaps:
        if f in (explain or {}):
            raise StepError(explain[f])
    if gaps:
        raise StepError("still needed: " + ", ".join(NEEDS[cfg["kind"]].get(f, f) for f in gaps))
    return st


def target(cfg: dict, step: str, approval_needed: bool = False) -> str | None:
    st = cfg["steps"][step]
    return st.get("to_when_approval_needed") if approval_needed and st.get("to_when_approval_needed") else st.get("to")


def signed(cfg: dict, step: str) -> str | None:
    return cfg["steps"][step].get("sign")


def rule(cfg: dict, name: str, default_value=None):
    return (cfg.get("rules") or {}).get(name, default_value)


def view(cfg: dict) -> dict:
    """The workflow as the page shows it: states, steps with their rules, in plain words."""
    out = copy.deepcopy(cfg)
    for name, st in out["steps"].items():
        st["needs"] = [NEEDS[cfg["kind"]].get(f, f) for f in st.get("required") or []]
        st["not_by_text"] = [WHO.get(f, f) for f in st.get("not_by") or []]
        st["permission_text"] = P.PERMISSIONS.get(st.get("permission"), "")
        st["who"] = st.get("roles") or sorted(r for r, perms in P.ROLE_PERMISSIONS.items()
                                              if st.get("permission") in perms)
        st["name"] = name
    return out
