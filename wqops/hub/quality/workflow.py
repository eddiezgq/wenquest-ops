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
            "disposition_reason": "reason", "owner": "owner", "item_code": "item", "supplier": "supplier",
            "quantity": "quantity affected", "severity": "severity"},
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

# what a company may change in a built-in step; everything else (where it starts and ends, whether it is an approval
# or a closing, its permission) is the shape WenQuest Ops carries out and stays as in the default
CHANGEABLE = {"label", "required", "not_by", "roles", "sign", "verb"}
NOT_BY_FIELDS = {"ncr": {"disposition_by", "created_by", "owner"}, "capa": {"owner", "created_by"}}


def _list(v) -> list:
    return v if isinstance(v, list) else []


def validate(cfg: dict, in_use: set[str] | None = None) -> list[str]:  # noqa: PLR0912, PLR0915
    """Everything wrong with a workflow, in plain words; empty when it may be saved. A workflow may rename states and
    steps, add what a step needs, add people who may not do a step, limit a step to roles, and tighten the rules; it
    keeps the shape of the default (which steps exist, from where to where, which are signed). ``in_use``: states that
    records are in now."""
    errs: list[str] = []
    kind = cfg.get("kind") if isinstance(cfg, dict) else None
    if kind not in KINDS:
        return [f"kind must be one of: {', '.join(KINDS)}"]
    base = default(kind)
    states, steps = cfg.get("states") or {}, cfg.get("steps") or {}
    num = cfg.get("numbering") or {}
    try:
        digits = int(num.get("digits") or 0)
    except (TypeError, ValueError):
        digits = 0
    if not str(num.get("prefix") or "").replace("-", "").isalnum() or not 3 <= digits <= 8:
        errs.append("numbering needs a prefix of letters or digits and 3 to 8 digits")
    if cfg.get("initial") != base["initial"]:
        errs.append(f"the first state stays {base['initial']}")
    if set(states) != set(base["states"]):
        errs.append("the states stay " + ", ".join(base["states"]) + " (their names on screen can change)")
    for s, v in base["states"].items():
        if s in states and bool((states[s] or {}).get("final")) != bool(v.get("final")):
            errs.append(f"state {s} stays {'final' if v.get('final') else 'open'}")
    for name in sorted(set(base["steps"]) - set(steps)):
        errs.append(f"step {name} is carried out by WenQuest Ops and cannot be removed")
    for name in sorted(set(steps) - set(base["steps"])):
        errs.append(f"step {name} is not a step WenQuest Ops can carry out")
    for name, want in base["steps"].items():
        st = steps.get(name)
        if not isinstance(st, dict):
            continue
        for key in sorted((set(want) | set(st)) - CHANGEABLE):
            if st.get(key) != want.get(key):
                errs.append(f"step {name}: {key} stays {want.get(key)!r}")
        if bool(str(st.get("sign") or "").strip()) != bool(want.get("sign")):
            errs.append(f"step {name}: " + ("approving and closing are signed with the person's password"
                                            if want.get("sign") else "only the steps WenQuest Ops signs can be signed"))
        req = _list(st.get("required"))
        for f in sorted(set(_list(want.get("required"))) - set(req)):
            errs.append(f"step {name}: it still needs {NEEDS[kind].get(f, f)}")
        for f in req:
            if f not in NEEDS[kind]:
                errs.append(f"step {name}: unknown field {f!r} in required")
        nb = _list(st.get("not_by"))
        missing_sep = set(_list(want.get("not_by"))) - set(nb)
        if missing_sep:
            errs.append(f"step {name}: {', '.join(WHO[x] for x in sorted(missing_sep))} may not do it; this "
                        "separation of duties cannot be removed")
        for x in nb:
            if x not in NOT_BY_FIELDS[kind]:
                errs.append(f"step {name}: {x!r} is not a person a {kind} record names")
        for r in _list(st.get("roles")):
            if r not in P.ROLE_PERMISSIONS:
                errs.append(f"step {name}: unknown role {r!r}")
        if "roles" in st and not _list(st.get("roles")):
            errs.append(f"step {name}: roles, when given, name at least one role")
        for key in ("required", "not_by", "roles"):
            if key in st and not isinstance(st[key], list):
                errs.append(f"step {name}: {key} is a list")
    for s in sorted((in_use or set()) - set(states)):
        errs.append(f"records are in state {s} now; a new version cannot remove it")
    rules = cfg.get("rules") or {}
    if kind == "ncr":
        for key in ("capa_closed_before_close", "eight_d_before_close"):
            if any(x not in SEVERITIES for x in _list(rules.get(key))):
                errs.append(f"rule {key}: severities are {', '.join(SEVERITIES)}")
        if "major" not in _list(rules.get("capa_closed_before_close")):
            errs.append("a major nonconformance closes only after its corrective action is closed; this cannot be "
                        "removed")
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
    made = conn.execute("insert into workflow_versions (kind, version, config, status, fingerprint, created_by, "
                        "enabled_by, enabled_at, note) values (%s, 1, %s, 'enabled', %s, 'WenQuest Ops', "
                        "'WenQuest Ops', now(), 'default workflow') on conflict (kind, version) do nothing "
                        "returning id",
                        (kind, Json(cfg), fingerprint(cfg))).fetchone()
    if made:                                    # records from before workflows were versioned run under version 1
        table = KINDS[kind]
        conn.execute(f"update {table} set workflow_version = %s where workflow_version is null",  # noqa: S608
                     (made["id"],))
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
                raise StepError(f"someone other than {WHO.get(f, f)} must "
                                + (st.get("verb") or f"do this ({st.get('label', step).lower()})"))
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
