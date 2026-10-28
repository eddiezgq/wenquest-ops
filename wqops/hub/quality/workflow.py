"""Quality workflows as configuration (ADR-0015, step 15a): loading a workflow, checking it against the red lines
of ADR-0010, versions pinned to records, and the guard every step of a record passes before it runs.

A workflow says which states a record has, which steps move it, who may run each step, what each step needs, whether
it is signed and who may not run it. The steps themselves are carried out by quality/records.py; this module decides
whether they may run. Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import yaml
from psycopg.types.json import Json

from wqops import i18n as I18N
from wqops.hub import permissions as P
from wqops.i18n import say

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
FIELD_TYPES = ("text", "number", "date", "choice", "person")
TOP_KEYS = {"kind", "label", "numbering", "initial", "states", "steps", "rules", "fields", "approvals"}
WHEN = {"ncr": {"severity": SEVERITIES, "disposition": None}, "capa": {"risk": ("low", "medium", "high"),
                                                                          "kind": ("corrective", "preventive")}}
NAME = re.compile(r"[a-z][a-z0-9_]{1,30}")
# steps a field may be needed before, and steps an extra approval may come before: not the steps that change a
# record's details, send it back or finish its 8D (a field needed there could never be filled, an approval there
# would stop a record going back)
GATES = {"ncr": {"contain", "disposition", "approve", "close", "cancel"},
         "capa": {"submit", "plan", "to_effectiveness", "effective", "cancel"}}
# where a record goes back a step; approvals given before it no longer count
BACK = {"ncr": ("disposition not approved",), "capa": ("not effective",)}


def _sep() -> str:
    return "、" if I18N.current() == "zh" else ", "


def _or() -> str:
    return "或" if I18N.current() == "zh" else " or "


def need_text(kind: str, f: str) -> str:
    """What a step needs, as the people using it say it, in the reader's language."""
    return I18N.label(NEEDS[kind].get(f, f))


def who_text(f: str) -> str:
    return I18N.label(WHO.get(f, f))


def well_formed(cfg) -> list[str]:
    """The structure a workflow needs before it can even be checked."""
    if not isinstance(cfg, dict):
        return [say("a workflow is a set of named parts")]
    errs = []
    for key, typ in (("states", dict), ("steps", dict), ("numbering", dict), ("rules", dict), ("fields", dict),
                     ("approvals", list)):
        if key in cfg and not isinstance(cfg[key], typ):
            errs.append(say("{key} has the wrong form", key=key))
    for key in ("states", "steps", "numbering"):
        if key not in cfg:
            errs.append(say("{key} is missing", key=key))
    for part in ("states", "steps", "fields"):
        if isinstance(cfg.get(part), dict) and any(not isinstance(v, dict) for v in cfg[part].values()):
            errs.append(say("every entry of {part} has named parts", part=part))
    if isinstance(cfg.get("approvals"), list):
        for a in cfg["approvals"]:
            if not isinstance(a, dict) or not isinstance(a.get("when", {}), dict) or \
                    any(not isinstance(v, list) for v in (a.get("when") or {}).values()):
                errs.append(say("every approval has named parts and its conditions are lists"))
                break
    return errs


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
        return [say("kind must be one of: {kinds}", kinds=", ".join(KINDS))]
    shape = well_formed(cfg)
    if shape:
        return shape
    base = default(kind)
    states, steps = cfg.get("states") or {}, cfg.get("steps") or {}
    num = cfg.get("numbering") or {}
    try:
        digits = int(num.get("digits") or 0)
    except (TypeError, ValueError):
        digits = 0
    if not str(num.get("prefix") or "").replace("-", "").isalnum() or not 3 <= digits <= 8:
        errs.append(say("numbering needs a prefix of letters or digits and 3 to 8 digits"))
    if cfg.get("initial") != base["initial"]:
        errs.append(say("the first state stays {state}", state=base["initial"]))
    if set(states) != set(base["states"]):
        errs.append(say("the states stay {states} (their names on screen can change)",
                        states=_sep().join(base["states"])))
    for s, v in base["states"].items():
        if s in states and bool((states[s] or {}).get("final")) != bool(v.get("final")):
            errs.append(say("state {s} stays final", s=s) if v.get("final") else say("state {s} stays open", s=s))
    for name in sorted(set(base["steps"]) - set(steps)):
        errs.append(say("step {name} is carried out by WenQuest Ops and cannot be removed", name=name))
    for name in sorted(set(steps) - set(base["steps"])):
        errs.append(say("step {name} is not a step WenQuest Ops can carry out", name=name))
    for name, want in base["steps"].items():
        st = steps.get(name)
        if not isinstance(st, dict):
            continue
        for key in sorted((set(want) | set(st)) - CHANGEABLE):
            if st.get(key) != want.get(key):
                errs.append(say("step {name}: {key} stays {value}", name=name, key=key, value=repr(want.get(key))))
        if bool(str(st.get("sign") or "").strip()) != bool(want.get("sign")):
            errs.append(say("step {name}: approving and closing are signed with the person's password", name=name)
                        if want.get("sign") else say("step {name}: only the steps WenQuest Ops signs can be signed",
                                                     name=name))
        req = _list(st.get("required"))
        for f in sorted(set(_list(want.get("required"))) - set(req)):
            errs.append(say("step {name}: it still needs {field}", name=name, field=need_text(kind, f)))
        for f in req:
            if f not in NEEDS[kind]:
                errs.append(say("step {name}: unknown field {field} in required", name=name, field=repr(f)))
        nb = _list(st.get("not_by"))
        missing_sep = set(_list(want.get("not_by"))) - set(nb)
        if missing_sep:
            errs.append(say("step {name}: {who} may not do it; this separation of duties cannot be removed",
                            name=name, who=_sep().join(who_text(x) for x in sorted(missing_sep))))
        for x in nb:
            if x not in NOT_BY_FIELDS[kind]:
                errs.append(say("step {name}: {person} is not a person a {kind} record names", name=name,
                                person=repr(x), kind=kind))
        for r in _list(st.get("roles")):
            if r not in P.ROLE_PERMISSIONS:
                errs.append(say("step {name}: unknown role {role}", name=name, role=repr(r)))
        if "roles" in st and not _list(st.get("roles")):
            errs.append(say("step {name}: roles, when given, name at least one role", name=name))
        for key in ("required", "not_by", "roles"):
            if key in st and not isinstance(st[key], list):
                errs.append(say("step {name}: {key} is a list", name=name, key=key))
    for key in sorted(set(cfg) - TOP_KEYS):
        errs.append(say("{key} is not part of a workflow", key=repr(key)))
    errs += _check_fields(kind, cfg, steps) + _check_approvals(kind, cfg, steps)
    for s in sorted((in_use or set()) - set(states)):
        errs.append(say("records are in state {s} now; a new version cannot remove it", s=s))
    rules = cfg.get("rules") or {}
    if kind == "ncr":
        for key in ("capa_closed_before_close", "eight_d_before_close"):
            if any(x not in SEVERITIES for x in _list(rules.get(key))):
                errs.append(say("rule {key}: severities are {list}", key=key, list=", ".join(SEVERITIES)))
        if "major" not in _list(rules.get("capa_closed_before_close")):
            errs.append(say("a major nonconformance closes only after its corrective action is closed; this cannot "
                            "be removed"))
    if kind == "capa" and rules.get("one_open_capa_per_ncr") is not True:
        errs.append(say("one open corrective action per nonconformance report cannot be removed"))
    return list(dict.fromkeys(errs))


def _check_fields(kind: str, cfg: dict, steps: dict) -> list[str]:
    errs = []
    fields = cfg.get("fields") or {}
    if not isinstance(fields, dict):
        return [say("fields is a list of named fields")]
    for name, raw in fields.items():
        f = raw if isinstance(raw, dict) else {}
        if not NAME.fullmatch(str(name)) or name in NEEDS[kind] or name in NOT_BY_FIELDS[kind]:
            errs.append(say("field {name}: a name of lower-case letters, digits and _ that WenQuest Ops does not use",
                            name=repr(name)))
        if not str(f.get("label") or "").strip():
            errs.append(say("field {name}: give it a label", name=name))
        if f.get("type") not in FIELD_TYPES:
            errs.append(say("field {name}: type is one of {types}", name=name, types=", ".join(FIELD_TYPES)))
        if f.get("type") == "choice" and not (isinstance(f.get("choices"), list) and len(f["choices"]) >= 2
                                              and all(str(c).strip() for c in f["choices"])):
            errs.append(say("field {name}: a choice field needs at least two choices", name=name))
        for st in _list(f.get("required_at")):
            if st not in GATES[kind]:
                errs.append(say("field {name}: it can be needed before {steps}, not {step}", name=name,
                                steps=", ".join(sorted(GATES[kind])), step=repr(st)))
        if f.get("type") == "choice" and any(not isinstance(c, str) for c in _list(f.get("choices"))):
            errs.append(say("field {name}: choices are words", name=name))
    return errs


def _check_approvals(kind: str, cfg: dict, steps: dict) -> list[str]:  # noqa: PLR0912
    errs, seen = [], set()
    approvals = cfg.get("approvals") or []
    if not isinstance(approvals, list):
        return [say("approvals is a list")]
    for raw in approvals:
        a = raw if isinstance(raw, dict) else {}
        name = str(a.get("name") or "")
        if not NAME.fullmatch(name) or name in seen:
            errs.append(say("approval {name}: a unique name of lower-case letters, digits and _", name=repr(name)))
        seen.add(name)
        if not str(a.get("label") or "").strip():
            errs.append(say("approval {name}: give it a label", name=name))
        if a.get("before") not in GATES[kind]:
            errs.append(say("approval {name}: it can come before {steps}, not {before}", name=name,
                            steps=", ".join(sorted(GATES[kind])), before=repr(a.get("before"))))
        if a.get("before") == "disposition" and "disposition" in (a.get("when") or {}):
            errs.append(say("approval {name}: the disposition is not known before it is submitted; put this "
                            "approval before approving or closing", name=name))
        if not str(a.get("sign") or "").strip():
            errs.append(say("approval {name}: an approval is signed; give the signature's meaning", name=name))
        roles = _list(a.get("roles"))
        if not roles or any(r not in P.ROLE_PERMISSIONS for r in roles):
            errs.append(say("approval {name}: name the roles that may approve", name=name))
        elif any("quality:view" not in P.ROLE_PERMISSIONS[r] for r in roles):
            errs.append(say("approval {name}: only roles that can see quality records can approve", name=name))
        for x in _list(a.get("not_by")):
            if x not in NOT_BY_FIELDS[kind]:
                errs.append(say("approval {name}: {person} is not a person a {kind} record names", name=name,
                                person=repr(x), kind=kind))
        for key, vals in (a.get("when") or {}).items():
            if key not in WHEN[kind]:
                errs.append(say("approval {name}: a condition on {key} is not possible", name=name, key=repr(key)))
            elif not _list(vals) or (WHEN[kind][key] and any(v not in WHEN[kind][key] for v in vals)):
                errs.append(say("approval {name}: {key} is one of {values}", name=name, key=key,
                                values=", ".join(WHEN[kind][key] or [say("the codes in use")])))
    return errs


def applies(a: dict, record: dict) -> bool:
    return all(record.get(k) in _list(v) for k, v in (a.get("when") or {}).items())


def clean_custom(cfg: dict, values: dict, people: set[str]) -> dict:
    """A company's own field values, checked against their definitions; an empty value removes the field."""
    fields = cfg.get("fields") or {}
    if not isinstance(values, dict):
        raise StepError(say("fields are given by name"))
    out = {}
    for name, given in values.items():
        if name not in fields:
            raise StepError(say("there is no field {name} in this workflow", name=repr(name)))
        f, v = fields[name], ("" if given is None else str(given).strip())
        if v == "":
            out[name] = None
        elif f["type"] == "number":
            try:
                out[name] = float(v)
            except ValueError as exc:
                raise StepError(say("{label}: a number", label=f['label'])) from exc
            if out[name] != out[name] or out[name] in (float("inf"), float("-inf")):
                raise StepError(say("{label}: a number", label=f['label']))
        elif f["type"] == "date":
            try:
                out[name] = dt.date.fromisoformat(v).isoformat()
            except ValueError as exc:
                raise StepError(say("{label}: a date like 2026-10-31", label=f['label'])) from exc
        elif f["type"] == "choice" and v not in f["choices"]:
            raise StepError(say("{label}: one of {choices}", label=f['label'], choices=', '.join(f['choices'])))
        elif f["type"] == "person" and v.lower() not in people:
            raise StepError(say("{label}: someone who can sign in", label=f['label']))
        else:
            out[name] = v.lower() if f["type"] == "person" else v[:2000]
    return out


def _sample(digits) -> str:
    """The first number with this many digits, for showing; a wrong value is shown as it is (validate refuses it)."""
    try:
        d = int(digits)
    except (TypeError, ValueError):
        return say("? ({digits} digits)", digits=repr(digits))
    return "0" * (d - 1) + "1" if 1 <= d <= 12 else say("? ({digits} digits)", digits=d)


def diff(old: dict, new: dict) -> list[str]:  # noqa: PLR0912 - one line per kind of change
    """What a new version changes, one line each, in plain words."""
    out = []
    if old.get("label") != new.get("label"):
        out.append(say("named {label}", label=repr(new.get("label"))))
    if old.get("numbering") != new.get("numbering"):
        o, n = old.get("numbering") or {}, new.get("numbering") or {}
        out.append(say("numbers: {old} -> {new}", old=f"{o.get('prefix')}-{_sample(o.get('digits'))}",
                       new=f"{n.get('prefix')}-{_sample(n.get('digits'))}"))
    for s, v in (new.get("states") or {}).items():
        if (old.get("states") or {}).get(s, {}).get("label") != v.get("label"):
            out.append(say("state {s}: named {label}", s=s, label=repr(v.get("label"))))
    for name, st in (new.get("steps") or {}).items():
        o = (old.get("steps") or {}).get(name) or {}
        for key in ("label", "sign", "verb"):
            if st.get(key) != o.get(key):
                out.append(say("step {name}: {key} {old} -> {new}", name=name, key=key, old=repr(o.get(key)),
                               new=repr(st.get(key))))
        for key in ("required", "not_by", "roles"):
            a, b = set(_list(o.get(key))), set(_list(st.get(key)))
            if b - a:
                out.append(say("step {name}: {key} adds {list}", name=name, key=key, list=", ".join(sorted(b - a))))
            if a - b:
                out.append(say("step {name}: {key} drops {list}", name=name, key=key, list=", ".join(sorted(a - b))))
    for key in sorted(set(old.get("rules") or {}) | set(new.get("rules") or {})):
        if (old.get("rules") or {}).get(key) != (new.get("rules") or {}).get(key):
            out.append(say("rule {key}: {old} -> {new}", key=key, old=repr((old.get("rules") or {}).get(key)),
                           new=repr((new.get("rules") or {}).get(key))))
    of_, nf = old.get("fields") or {}, new.get("fields") or {}
    for name in sorted(set(of_) | set(nf)):
        if name not in of_:
            out.append(say("new field {name} ({label}, {type})", name=name, label=nf[name].get("label"),
                           type=nf[name].get("type")))
        elif name not in nf:
            out.append(say("field {name} removed (values already entered stay on the records)", name=name))
        elif of_[name] != nf[name]:
            out.append(say("field {name} changed", name=name))
    oa = {a.get("name"): a for a in old.get("approvals") or []}
    na = {a.get("name"): a for a in new.get("approvals") or []}
    for name in sorted(set(oa) | set(na)):
        if name not in oa:
            when = "".join(say(", when {key} is {values}", key=k, values=_or().join(_list(v)))
                           for k, v in (na[name].get("when") or {}).items())
            out.append(say("new approval {name}: {label} before {before}, by {roles}{when}", name=name,
                           label=na[name].get("label"), before=na[name].get("before"),
                           roles=", ".join(_list(na[name].get("roles"))), when=when))
        elif name not in na:
            out.append(say("approval {name} removed", name=name))
        elif oa[name] != na[name]:
            out.append(say("approval {name} changed", name=name))
    return out


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
        raise WorkflowError(say("the default {kind} workflow is wrong: {bad}", kind=kind, bad='; '.join(bad)))
    made = conn.execute("insert into workflow_versions (kind, version, config, status, fingerprint, created_by, "
                        "enabled_by, enabled_at, note) values (%s, 1, %s, 'enabled', %s, 'WenQuest Ops', "
                        "'WenQuest Ops', now(), %s) on conflict (kind, version) do nothing "
                        "returning id",
                        (kind, Json(cfg), fingerprint(cfg), say("default workflow"))).fetchone()
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
    return say("record state::" + state.replace("_", " "))


def check(cfg: dict, record: dict, step: str, user: dict | None, facts: dict | None = None,  # noqa: PLR0912
          *, name_field: str = "name", explain: dict | None = None) -> dict:
    """May ``user`` run ``step`` on ``record`` now? Raises StepError or NotAllowed with what is wrong; returns the
    step's configuration. ``facts``: values the step brings or computes (fields typed in, actions done, ...);
    ``explain``: a fuller message for a missing field. The signature itself is checked by the caller, before its
    transaction (records.check_signer)."""
    st = cfg["steps"].get(step)
    if st is None:
        raise StepError(say("this workflow has no step {step}", step=step))
    if record["status"] not in st["from"]:
        raise StepError(say("{record} is {cfg}; this step needs it to be {v}",
                            record=record[name_field], cfg=_label(cfg, record['status']),
                            v=_or().join(_label(cfg, s) for s in st['from'])))
    if user is not None:
        roles = user.get("roles") or []
        if roles and st.get("permission") and not P.allows(roles, st["permission"]):
            raise NotAllowed(say("your role does not allow: {PERMISSIONS}",
                                 PERMISSIONS=P.PERMISSIONS[st['permission']]))
        if st.get("roles") and roles and not set(roles) & set(st["roles"]):
            raise NotAllowed(say("{st}: only {roles} may do this",
                                 st=st.get('label', step), roles=', '.join(st['roles'])))
        for f in st.get("not_by") or []:
            if record.get(f) and record.get(f) == user.get("email"):
                raise StepError(say("someone other than {who} must {verb}", who=who_text(f),
                                    verb=st.get("verb") or say("do this ({label})",
                                                               label=st.get("label", step).lower())))
    values = {**record, **(facts or {})}
    custom = {**(record.get("custom") or {}), **((facts or {}).get("custom") or {})}
    for name, f in (cfg.get("fields") or {}).items():
        if step in _list(f.get("required_at")) and custom.get(name) in (None, ""):
            raise StepError(say("still needed: {label}", label=f['label']))
    done = set((facts or {}).get("approvals_done") or ())
    for a in cfg.get("approvals") or []:
        if a["before"] == step and applies(a, values) and a["name"] not in done:
            raise StepError(say("{label} is needed first (signed by {roles})",
                                label=a['label'], roles=_or().join(a['roles'])))
    gaps = [f for f in st.get("required") or [] if values.get(f) in (None, "", [], False, 0)]
    for f in gaps:
        if f in (explain or {}):
            raise StepError(explain[f])
    if gaps:
        raise StepError(say("still needed: {list}", list=_sep().join(need_text(cfg["kind"], f) for f in gaps)))
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
    out.setdefault("fields", {})
    out.setdefault("approvals", [])
    for name, st in out["steps"].items():
        st["needs"] = [need_text(cfg["kind"], f) for f in st.get("required") or []]
        st["not_by_text"] = [who_text(f) for f in st.get("not_by") or []]
        st["permission_text"] = I18N.label(P.PERMISSIONS.get(st.get("permission"), ""))
        st["who"] = st.get("roles") or sorted(r for r, perms in P.ROLE_PERMISSIONS.items()
                                              if st.get("permission") in perms)
        st["name"] = name
    return out
