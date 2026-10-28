"""Workflow changes proposed from the company's procedures (ADR-0015, step 15c): the shape of one proposed change,
how it is applied to a workflow, the checks code makes on it, and the decisions people take.

The model (quality/workflow_ai.py) proposes; this module decides what may be offered and carries out what a person
accepts. A change can be accepted only when code found its quote in the procedure it names, it changes something,
and the workflow it makes passes the red lines. An accepted change goes into the draft version (made from the
enabled version when there is none); someone who did not change that draft enables it with a signature (15b).
Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import copy
import re

from psycopg.types.json import Json

from wqops import i18n as I18N
from wqops.hub.docs import classify as C
from wqops.hub.quality import records as Q
from wqops.hub.quality import workflow as W
from wqops.hub.quality import workflow_admin as WA
from wqops.i18n import say

OPS = {
    "require": "a step needs a field the record already has",
    "not_by": "a person named on the record may not do a step",
    "roles": "only some of the roles that may do a step now may do it",
    "rule": "a severity closes only after its corrective action is closed, or after its 8D",
    "field": "a field of the company's own, maybe needed before a step",
    "approval": "an extra signed approval before a step, maybe only under a condition",
    "numbering": "the record numbers' prefix and digits",
}
RULES = ("capa_closed_before_close", "eight_d_before_close")
MIN_QUOTE = 15                                   # a quote needs more than a few words to rest on
MAX_ITEMS = 30
MAX_READ = 30000                                 # characters of one procedure the model reads
MAX_TOTAL = 80000
PROCEDURE_TYPES = ("procedure", "work_instruction", "form")
# only procedures approved in the library: a draft anyone with documents:edit uploaded is not what the company follows
READABLE = ("effective",)
# fields a person can still fill in, by the state a record is in (a field needed before a step must be fillable in
# every state the step starts from, or records would get stuck); the steps' own inputs are not proposals
FILLABLE = {"ncr": {s: ("owner", "severity") for s in ("open", "contained", "pending_approval", "dispositioned")},
            "capa": Q.EDITABLE}


def _sep() -> str:
    return "、" if I18N.current() == "zh" else ", "


def _or() -> str:
    return "或" if I18N.current() == "zh" else " or "


class ChangeError(ValueError):
    """A proposed change is not in a shape WenQuest Ops can apply."""


def _s(v, n: int = 200) -> str:
    return str(v if v is not None else "").strip()[:n]


def _names(v) -> list[str]:
    if isinstance(v, str):
        v = [v]
    return [_s(x, 60) for x in v if _s(x, 60)] if isinstance(v, list) else []


def _when(v) -> dict:
    if v in (None, {}):
        return {}
    if not isinstance(v, dict):
        raise ChangeError(say("the conditions of an approval are given by name"))
    out = {_s(k, 40): _names(x) for k, x in v.items()}
    if any(not x for x in out.values()):
        raise ChangeError(say("every condition of an approval names at least one value"))
    return out


def clean(kind: str, raw: dict) -> dict:  # noqa: PLR0911 - one shape per kind of change
    """A change in the shape it is stored and applied in; ChangeError when it cannot be made sense of."""
    if not isinstance(raw, dict) or not isinstance(raw.get("op"), str) or raw["op"] not in OPS:
        raise ChangeError(say("a change is one of: {OPS}", OPS=', '.join(OPS)))
    op = raw["op"]
    if op in ("require", "not_by", "roles") and _s(raw.get("step")) not in W.BUILT_IN[kind]:
        raise ChangeError(say("there is no step {raw}", raw=repr(_s(raw.get('step')))))
    if op == "require":
        return {"op": op, "step": _s(raw["step"]), "field": _s(raw.get("field"))}
    if op == "not_by":
        return {"op": op, "step": _s(raw["step"]), "person": _s(raw.get("person"))}
    if op == "roles":
        return {"op": op, "step": _s(raw["step"]), "roles": sorted(set(_names(raw.get("roles"))))}
    if op == "rule":
        if kind != "ncr" or _s(raw.get("rule")) not in RULES:
            raise ChangeError(say("rules that can be proposed: {RULES} (nonconformance reports)",
                                  RULES=', '.join(RULES)))
        return {"op": op, "rule": _s(raw["rule"]), "severity": _s(raw.get("severity"))}
    if op == "field":
        out = {"op": op, "name": _s(raw.get("name"), 40), "label": _s(raw.get("label"), 80),
               "type": _s(raw.get("type"), 20), "required_at": sorted(set(_names(raw.get("required_at"))))}
        if out["type"] == "choice":
            out["choices"] = list(dict.fromkeys(_names(raw.get("choices"))))
        return out
    if op == "approval":
        return {"op": op, "name": _s(raw.get("name"), 40), "label": _s(raw.get("label"), 80),
                "before": _s(raw.get("before")), "roles": sorted(set(_names(raw.get("roles")))),
                "when": _when(raw.get("when")),
                "not_by": sorted(set(_names(raw.get("not_by")))),
                "sign": _s(raw.get("sign"), 120) or _s(raw.get("label"), 80)}
    digits = raw.get("digits")
    if isinstance(digits, str) and digits.strip().isdigit():
        digits = int(digits)
    if type(digits) is not int or not 3 <= digits <= 8:
        raise ChangeError(say("numbering needs 3 to 8 digits"))
    return {"op": op, "prefix": _s(raw.get("prefix"), 20), "digits": digits}


def apply(cfg: dict, ch: dict) -> dict:
    """The workflow with this change made (a copy). Adding what is already there changes nothing."""
    out = copy.deepcopy(cfg)
    op = ch["op"]
    if op in ("require", "not_by"):
        key, val = ("required", ch["field"]) if op == "require" else ("not_by", ch["person"])
        st = out["steps"][ch["step"]]
        if val not in (st.get(key) or []):
            st[key] = [*(st.get(key) or []), val]
    elif op == "roles":
        out["steps"][ch["step"]]["roles"] = list(ch["roles"])
    elif op == "rule":
        rules = out.setdefault("rules", {})
        if ch["severity"] not in (rules.get(ch["rule"]) or []):
            rules[ch["rule"]] = [*(rules.get(ch["rule"]) or []), ch["severity"]]
    elif op == "field":
        f = {"label": ch["label"], "type": ch["type"]}
        if "choices" in ch:
            f["choices"] = ch["choices"]
        if ch["required_at"]:
            f["required_at"] = ch["required_at"]
        out.setdefault("fields", {})[ch["name"]] = f
    elif op == "approval":
        a = {"name": ch["name"], "label": ch["label"], "before": ch["before"], "roles": ch["roles"], "sign": ch["sign"]}
        if ch["when"]:
            a["when"] = ch["when"]
        if ch["not_by"]:
            a["not_by"] = ch["not_by"]
        approvals = [x for x in out.get("approvals") or [] if x.get("name") != ch["name"]]
        out["approvals"] = [*approvals, a]
    elif op == "numbering":
        out["numbering"] = {"prefix": ch["prefix"], "digits": ch["digits"]}
    return out


def _clash(cfg: dict, ch: dict) -> str | None:
    """A field or approval of the same name that is something else: the change would replace it."""
    if ch["op"] == "field" and ch["name"] in (cfg.get("fields") or {}):
        if apply(cfg, ch)["fields"][ch["name"]] != cfg["fields"][ch["name"]]:
            return say("the workflow already has a field {name} that is different; change it by hand",
                       name=repr(ch["name"]))
    if ch["op"] == "approval":
        old = next((a for a in cfg.get("approvals") or [] if a.get("name") == ch["name"]), None)
        if old is not None and old != next(a for a in apply(cfg, ch)["approvals"] if a["name"] == ch["name"]):
            return say("the workflow already has an approval {name} that is different; change it by hand",
                       name=repr(ch["name"]))
    return None


def allowed_now(cfg: dict, step: str) -> set[str]:
    """The roles that may do a step under this workflow."""
    st = cfg["steps"][step]
    return set(st.get("roles") or W.view(cfg)["steps"][step]["who"])


def _loosens(cfg: dict, ch: dict) -> str | None:
    """A proposal only tightens: it may not let more roles do a step, nor need a field no one can fill in."""
    if ch["op"] == "roles":
        more = set(ch["roles"]) - allowed_now(cfg, ch["step"])
        if more:
            label = cfg["steps"][ch["step"]].get("label", ch["step"]).lower()
            return say("it would let {roles} {step}; a suggestion can only limit who may do a step",
                       roles=", ".join(sorted(more)), step=label)
    if ch["op"] == "require" and ch["field"] in W.NEEDS[cfg["kind"]] and \
            ch["field"] not in (cfg["steps"][ch["step"]].get("required") or []):
        st = cfg["steps"][ch["step"]]
        fillable = [set(FILLABLE[cfg["kind"]].get(s, ())) for s in st["from"]]
        if ch["step"] == "cancel" or not fillable or ch["field"] not in set.intersection(*fillable):
            return say("{field} cannot be filled in before {step}; records would get stuck",
                       field=W.need_text(cfg["kind"], ch["field"]), step=st.get("label", ch["step"]).lower())
    return None


def quoted(quote: str, body: str) -> bool:
    q = C.norm(quote)
    return len(q) >= MIN_QUOTE and q in C.norm(body)


def check(cfg: dict, ch: dict, quote: str, body: str | None, in_use: set[str] | None = None) -> dict:
    """What code finds about one change against ``cfg``: {verified, problems, already, lines}. ``body``: the text of
    the procedure it quotes (None when it names no procedure that was read)."""
    problems = []
    verified = body is not None and quoted(quote, body)
    if body is None:
        problems.append(say("it does not name one of the procedures that were read"))
    elif not verified:
        problems.append(say("its quote is not in the procedure it names") if len(C.norm(quote)) >= MIN_QUOTE
                        else say("its quote is too short to rest on"))
    if ch["op"] == "numbering" and verified and not re.search(
            rf"(?<![a-z0-9]){re.escape(C.norm(ch['prefix']))}(?![a-z0-9])", C.norm(quote)):
        problems.append(say("the quote does not show the prefix {prefix}", prefix=ch["prefix"]))
    clash = _clash(cfg, ch)
    if clash:
        problems.append(clash)
    loose = _loosens(cfg, ch)
    if loose:
        problems.append(loose)
    new = apply(cfg, ch)
    lines = W.diff(cfg, new)
    before = set(W.validate(cfg, in_use))
    problems += [e for e in W.validate(new, in_use) if e not in before]
    return {"verified": verified, "problems": list(dict.fromkeys(problems)), "already": not lines and not clash,
            "lines": lines}


def describe(ch: dict, cfg: dict) -> str:
    """One change in plain words, for the page and the draft's history."""
    s = _describe(ch, cfg)
    return s[:1].upper() + s[1:]


def _describe(ch: dict, cfg: dict) -> str:  # noqa: PLR0911 - one sentence per kind of change
    kind = cfg["kind"]

    def step(s):
        return (cfg["steps"].get(s) or {}).get("label", s)

    op = ch["op"]
    if op == "require":
        return say("{step} needs {field}", step=step(ch["step"]), field=W.need_text(kind, ch["field"]))
    if op == "not_by":
        return say("{who} may not {step}", who=W.who_text(ch["person"]), step=step(ch["step"]).lower())
    if op == "roles":
        return say("only {roles} may {step}", roles=_or().join(ch["roles"]), step=step(ch["step"]).lower())
    if op == "rule":
        if ch["rule"] == "capa_closed_before_close":
            return say("{severity} reports close only after a closed corrective action", severity=ch["severity"])
        return say("{severity} reports close only after a completed 8D", severity=ch["severity"])
    if op == "field":
        if ch["required_at"]:
            return say("new field {label} ({type}), needed before {steps}", label=ch["label"], type=ch["type"],
                       steps=_sep().join(step(s).lower() for s in ch["required_at"]))
        return say("new field {label} ({type})", label=ch["label"], type=ch["type"])
    if op == "approval":
        when = "".join(say(" when {key} is {values}", key=k, values=_or().join(v)) for k, v in ch["when"].items())
        return say("{label}: signed by {roles} before {step}{when}", label=ch["label"], roles=_or().join(ch["roles"]),
                   step=step(ch["before"]).lower(), when=when)
    return say("numbers {sample}", sample=f"{ch['prefix']}-{'0' * (max(ch['digits'], 1) - 1)}1")


# ---------------------------------------------------------------- procedures the model may read

def procedures(conn, kind: str) -> list[dict]:
    """Procedures, work instructions and forms in the library with text; the ones about this kind of record first."""
    near = {"ncr": ("nonconformance", "receiving"), "capa": ("capa", "nonconformance")}[kind]
    rows = conn.execute(
        "select d.id, d.number, d.title, d.revision, d.status, d.doc_type, d.process, d.original_name, d.sha256, "
        "d.text_chars from documents d where d.doc_type = any(%s) and d.status = any(%s) and d.text_chars > 0 "
        "and d.duplicate_of is null order by d.number nulls last, d.id",
        (list(PROCEDURE_TYPES), list(READABLE))).fetchall()
    out = [dict(r, suggested=r["process"] in near) for r in rows]
    return sorted(out, key=lambda r: (not r["suggested"], r["status"] != "effective"))


def read(conn, kind: str, ids: list[int]) -> list[dict]:
    """The procedures the model will read, with their text cut to what it may read."""
    allowed = {r["id"]: r for r in procedures(conn, kind)}
    if not ids:
        raise WA.AdminError(say("choose the procedures to read"))
    if len(ids) > 8:
        raise WA.AdminError(say("choose at most 8 procedures at a time"))
    out, total = [], 0
    for i in dict.fromkeys(ids):
        if i not in allowed:
            raise WA.AdminError(say("document {i} is not a procedure, work instruction or form of the library with "
                                    "text",
                                    i=i))
        body = conn.execute("select body from doc_text where document_id = %s", (i,)).fetchone()["body"]
        room = max(0, min(MAX_READ, MAX_TOTAL - total))
        d = allowed[i]
        out.append({"id": i, "name": " ".join(x for x in (d["number"], d["title"]) if x) or d["original_name"],
                    "revision": d["revision"], "status": d["status"], "sha256": d["sha256"],
                    "chars": len(body), "cut": len(body) > room, "text": body[:room]})
        total += min(len(body), room)
    return out


# ---------------------------------------------------------------- storing what the model proposed

def _doc(v) -> int | None:
    return v if type(v) is int else None


def store(conn, kind: str, email: str, docs: list[dict], result: dict, ai_run: int | None,  # noqa: PLR0917
          base_id: int | None = None) -> dict:
    """Keep a proposal: every change with what code found about it against the version the model was shown.
    ``result``: {"changes": [{change, document_id, quote, why}], "cannot": [...], "summary"}; anything in it may be
    malformed (it comes from the model) and is kept with the problem found."""
    changes = result.get("changes") if isinstance(result.get("changes"), list) else []
    raw_cannot = result.get("cannot") if isinstance(result.get("cannot"), list) else []
    summary = _s(result.get("summary"), 2000)
    if len(changes) > MAX_ITEMS:
        summary += say(" (The AI suggested {n} changes; the first {max} are kept.)", n=len(changes), max=MAX_ITEMS)
    with conn.transaction():
        base = W.version(conn, kind, base_id)
        bodies = {d["id"]: d["text"] for d in docs}
        uses = WA.in_use(conn, kind)
        cannot = []
        for c in raw_cannot[:MAX_ITEMS]:
            if not isinstance(c, dict):
                continue
            doc = _doc(c.get("document_id"))
            cannot.append({"document_id": doc if doc in bodies else None, "quote": _s(c.get("quote"), 600),
                           "why": _s(c.get("why"), 600),
                           "verified": doc in bodies and quoted(_s(c.get("quote"), 600), bodies[doc])})
        p = conn.execute(
            "insert into workflow_proposals (kind, base_version, documents, created_by, ai_run, summary, cannot) "
            "values (%s, %s, %s, %s, %s, %s, %s) returning *",
            (kind, base["id"], Json([{k: d[k] for k in ("id", "name", "revision", "status", "sha256", "chars", "cut")}
                                     for d in docs]), email, ai_run, summary, Json(cannot))).fetchone()
        for seq, raw in enumerate(changes[:MAX_ITEMS], 1):
            item = raw if isinstance(raw, dict) else {}
            quote, doc = _s(item.get("quote"), 1000), _doc(item.get("document_id"))
            try:
                ch = clean(kind, item.get("change"))
                found = check(base["config"], ch, quote, bodies.get(doc), uses)
            except ChangeError as exc:
                ch = {k: _s(v, 200) for k, v in item["change"].items()} if isinstance(item.get("change"), dict) else {}
                found = {"verified": doc in bodies and quoted(quote, bodies[doc]), "problems": [str(exc)],
                         "already": False, "lines": []}
            conn.execute(
                "insert into workflow_proposal_items (proposal_id, seq, change, document_id, quote, why, verified, "
                "problems, already, lines) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (p["id"], seq, Json(ch), doc if doc in bodies else None, quote, _s(item.get("why"), 1000),
                 found["verified"], Json(found["problems"]), found["already"], Json(found["lines"])))
    return p


def get(conn, pid: int) -> dict:
    row = conn.execute("select * from workflow_proposals where id = %s", (pid,)).fetchone()
    if row is None:
        raise KeyError(pid)
    return row


def items(conn, pid: int) -> list[dict]:
    return conn.execute("select * from workflow_proposal_items where proposal_id = %s order by seq", (pid,)).fetchall()


def acceptable(item: dict) -> bool:
    return item["decision"] == "open" and item["verified"] and not item["problems"] and not item["already"]


def view(conn, p: dict) -> dict:
    """A proposal as the page shows it, with each change described and whether it may be accepted now."""
    base = W.version(conn, p["kind"], p["base_version"])
    enabled = W.ensure(conn, p["kind"])
    draft = conn.execute("select id, version from workflow_versions where kind = %s and status = 'draft'",
                         (p["kind"],)).fetchone()
    docs = {d["id"]: d for d in p["documents"]}
    out_items = []
    for it in items(conn, p["id"]):
        try:
            text = describe(clean(p["kind"], it["change"]), base["config"])
        except (ChangeError, KeyError):
            text = say("a change WenQuest Ops cannot make")
        out_items.append({**{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in it.items()},
                          "text": text, "document": docs.get(it["document_id"]), "acceptable": acceptable(it)})
    return {**{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in p.items()},
            "base": base["version"], "enabled": enabled["version"], "draft": draft, "items": out_items,
            "cannot": [dict(c, document=docs.get(c.get("document_id"))) for c in p["cannot"]]}


def listing(conn, kind: str) -> list[dict]:
    rows = conn.execute(
        "select p.id, p.created_at, p.created_by, p.summary, p.documents, count(i.id) as changes, "
        "count(i.id) filter (where i.decision = 'open' and i.verified and i.problems = '[]'::jsonb and not i.already) "
        "as open, count(i.id) filter (where i.decision = 'accepted') as accepted from workflow_proposals p left join "
        "workflow_proposal_items i on i.proposal_id = p.id where p.kind = %s group by p.id order by p.id desc limit 20",
        (kind,)).fetchall()
    return [dict(r, created_at=r["created_at"].isoformat()) for r in rows]


# ---------------------------------------------------------------- decisions

def _item(conn, iid: int) -> tuple[dict, dict]:
    it = conn.execute("select * from workflow_proposal_items where id = %s for update", (iid,)).fetchone()
    if it is None:
        raise KeyError(iid)
    if it["decision"] != "open":
        raise WA.AdminError(say("this change was already {decision} by {decided_by}",
                                decision=it['decision'], decided_by=it['decided_by']))
    return it, get(conn, it["proposal_id"])


def accept(conn, iid: int, email: str, note: str = "") -> dict:
    """Put one proposed change into the draft (made from the enabled version when there is none). The person who
    accepts it has changed the draft, so someone else enables it."""
    with conn.transaction():
        it, p = _item(conn, iid)
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"wqo-workflow:{p['kind']}",))
        if not acceptable(it):
            raise WA.AdminError(say("only a change whose quote was found and that passes the checks can be accepted"))
        ch = clean(p["kind"], it["change"])
        draft = conn.execute("select * from workflow_versions where kind = %s and status = 'draft' for update",
                             (p["kind"],)).fetchone() or WA.new_draft(conn, p["kind"], email)
        # checked again on the draft as it is now: it may differ from the version the model compared with (the quote
        # was found in the procedure when the proposal was made and is kept unchanged, so it is its own text here)
        found = check(draft["config"], ch, it["quote"], it["quote"], WA.in_use(conn, p["kind"]))
        if found["problems"]:
            raise WA.AdminError(say("in the draft as it is now: {list}", list="; ".join(found["problems"])))
        now = conn.execute("select status from documents where id = %s", (it["document_id"],)).fetchone()
        if now is None or now["status"] not in READABLE:
            raise WA.AdminError(say("the procedure it quotes is no longer in effect in the document library"))
        errors = W.validate(apply(draft["config"], ch), WA.in_use(conn, p["kind"]))
        if errors:
            raise WA.AdminError(say("fix the draft first: {list}", list="; ".join(errors)))
        doc = next((d["name"] for d in p["documents"] if d["id"] == it["document_id"]), say("a procedure"))
        if found["already"]:
            WA.log(conn, draft["id"], email, say("proposal accepted"),
                   say("already in the draft: {change} ({doc})", change=describe(ch, draft["config"]), doc=doc))
        else:
            WA.save(conn, draft["id"], email, apply(draft["config"], ch))
            WA.log(conn, draft["id"], email, say("proposal accepted"),
                   say("{change}; {doc}: \"{quote}\"", change=describe(ch, draft["config"]), doc=doc,
                       quote=it["quote"][:600]))
        return conn.execute(
            "update workflow_proposal_items set decision = 'accepted', decided_by = %s, decided_at = now(), "
            "decision_note = %s, draft_version = %s where id = %s returning *",
            (email, _s(note, 1000) or None, draft["id"], iid)).fetchone()


def reject(conn, iid: int, email: str, reason: str = "") -> dict:
    with conn.transaction():
        _item(conn, iid)
        return conn.execute(
            "update workflow_proposal_items set decision = 'rejected', decided_by = %s, decided_at = now(), "
            "decision_note = %s where id = %s returning *", (email, _s(reason, 1000) or None, iid)).fetchone()
