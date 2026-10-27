"""Setting the quality system up for the company (ADR-0016, step 16d): a short questionnaire whose answers propose
what does not apply; changes proposed from the company's own procedures (by the model, system/setup_ai.py), each
quoting the procedure, checked here and decided by a person; and procedures written from the workflow in use, by
code from templates, so that what the procedure says is what the system does.

Plain code: no AI, no network (tests/test_isolation.py). Every change goes through the functions people use by hand
(qms.declare, qms.set_setting, qms.link), with the same checks and signatures.
"""

from __future__ import annotations

import datetime as dt
import io

from psycopg.types.json import Json

from wqops.hub.docs import library as LIB
from wqops.hub.quality import records as Q
from wqops.hub.quality import workflow as W
from wqops.hub.quality import workflow_proposals as WP
from wqops.hub.system import qms as QMS
from wqops.hub.system import rules as R
from wqops.i18n import say

# ---------------------------------------------------------------- the questionnaire

def questions(conn, standard: str) -> dict:
    """The questionnaire of the standard's pack: the one adopted, or the pack file before it is adopted (or when the
    adopted pack is older than questionnaires in packs)."""
    row = QMS.enabled(conn, standard)
    return (row and row["content"].get("questions")) or QMS.load(standard).get("questions") or {}


class SetupError(ValueError):
    pass


def clean_answers(qs: dict, raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise SetupError(say("answers are given by question"))
    out = {}
    for k, v in raw.items():
        q = qs.get(k)
        if q is None:
            raise SetupError(say("there is no question {k}", k=repr(k)))
        if v in (None, ""):
            continue
        if q["type"] == "yesno":
            if type(v) is not bool:
                raise SetupError(say("{label} yes or no", label=q['label']))
            out[k] = v
        elif q["type"] == "number":
            if type(v) is not int or not 0 < v < 1_000_000:
                raise SetupError(say("{label}: a whole number", label=q['label']))
            out[k] = v
        else:
            out[k] = str(v).strip()[:500]
    return out


def answers(conn, standard: str) -> dict:
    r = conn.execute("select answers, email, at from qms_setup where standard = %s order by id desc limit 1",
                     (standard,)).fetchone()
    return {"answers": r["answers"], "email": r["email"], "at": r["at"].isoformat()} if r else {"answers": {}}


def save_answers(conn, email: str, standard: str, raw: dict) -> dict:
    vals = clean_answers(questions(conn, standard), raw)
    conn.execute("insert into qms_setup (standard, answers, email) values (%s, %s, %s)", (standard, Json(vals), email))
    return vals


def proposed_applicability(conn, standard: str) -> list[dict]:
    """What the answers say does not apply (or does), against what is declared now."""
    vals = answers(conn, standard)["answers"]
    now = QMS.applicability(conn, standard)
    out = []
    for k, q in questions(conn, standard).items():
        if not q.get("if_no") or k not in vals:
            continue
        for control, reason in q["if_no"].items():
            applies = bool(vals[k])
            why = reason if not applies else f"Answered yes: {q['label'].rstrip('?').lower()}."
            current = now.get(control)
            out.append({"control": control, "applies": applies, "reason": why, "question": q["label"],
                        "same": bool(current) and current["applies"] == applies})
    return out


def apply_answers(conn, user: dict, standard: str, password: str, today: dt.date,  # noqa: PLR0917
                  tz: str = "UTC") -> int:
    """Declare, with the person's signature, what the answers say; only what differs from now."""
    todo = [p for p in proposed_applicability(conn, standard) if not p["same"]]
    if not todo:
        raise SetupError(say("the declarations already match the answers"))
    for p in todo:
        QMS.declare(conn, user, standard, p["control"], p["applies"], p["reason"], password, today, tz)
    return len(todo)


# ---------------------------------------------------------------- changes proposed from the procedures

KINDS = {"setting": "a number of days or one of our own rules switched on or off",
         "applies": "a requirement that does not apply (or does), with the reason",
         "evidence": "a procedure that shows how a requirement is met"}
MAX_ITEMS = 30


def clean(pack: dict, raw: dict) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("kind"), str) or raw["kind"] not in KINDS:
        raise SetupError(say("a change is one of: {KINDS}", KINDS=', '.join(KINDS)))
    k = raw["kind"]
    cs = QMS.controls(pack)
    if k == "setting":
        key = str(raw.get("key") or "")
        spec = (pack.get("settings") or {}).get(key)
        if spec is None:
            raise SetupError(say("there is no setting {key}", key=repr(key)))
        v = raw.get("value")
        if type(spec["value"]) is bool:
            if type(v) is not bool:
                raise SetupError(say("{label}: yes or no", label=spec['label']))
        elif type(v) is not int or not spec.get("min", 0) <= v <= spec.get("max", 3650):
            raise SetupError(say("{label}: a whole number from {spec} to {spec2}",
                                 label=spec['label'], spec=spec.get('min', 0), spec2=spec.get('max', 3650)))
        return {"kind": k, "key": key, "value": v}
    control = str(raw.get("control") or "")
    if control not in cs:
        raise SetupError(say("there is no requirement {control}", control=repr(control)))
    if k == "applies":
        if not cs[control].get("may_exclude"):
            raise SetupError(say("this requirement always applies"))
        if type(raw.get("applies")) is not bool or not str(raw.get("reason") or "").strip():
            raise SetupError(say("say whether it applies and why"))
        return {"kind": k, "control": control, "applies": raw["applies"], "reason": str(raw["reason"]).strip()[:500]}
    if cs[control]["rule"] not in R.LINKED and not cs[control].get("switch"):
        raise SetupError(say("this requirement is judged from the records, not from a document"))
    return {"kind": k, "control": control}


def describe(pack: dict, ch: dict) -> str:
    """One proposed change in plain words; anything malformed reads as a change WenQuest Ops cannot make."""
    try:
        clean(pack, ch)
    except (SetupError, TypeError, ValueError, KeyError):
        return "A change WenQuest Ops cannot make: " + ", ".join(f"{k} {v}" for k, v in ch.items())[:200]
    if ch["kind"] == "setting":
        spec = pack["settings"][ch["key"]]
        v = ("on" if ch["value"] else "off") if type(ch["value"]) is bool else ch["value"]
        return f"{spec['label']}: {v}"
    c = QMS.controls(pack)[ch["control"]]
    if ch["kind"] == "applies":
        return f"{'Applies' if ch['applies'] else 'Does not apply'}: {c['summary']}"
    return f"Evidence for: {c['summary']}"


def check(conn, standard: str, pack: dict, ch: dict, doc_id: int | None, quote: str,  # noqa: PLR0917
          body: str | None) -> dict:
    problems = []
    verified = body is not None and WP.quoted(quote, body)
    if body is None:
        problems.append("it does not name one of the procedures that were read")
    elif not verified:
        problems.append("its quote is not in the procedure it names")
    already = False
    if ch["kind"] == "setting":
        already = QMS.settings(conn, standard, pack).get(ch["key"]) == ch["value"]
    elif ch["kind"] == "applies":
        now = QMS.applicability(conn, standard).get(ch["control"])
        already = bool(now) and now["applies"] == ch["applies"]
    else:
        already = doc_id in {d["id"] for d in QMS.evidence(conn, standard).get(ch["control"], [])}
    return {"verified": verified, "problems": problems, "already": already}


def store(conn, email: str, standard: str, docs: list[dict], result: dict,  # noqa: PLR0917
          ai_run: int | None) -> dict:
    row = QMS.enabled(conn, standard)
    if row is None:
        raise QMS.QmsError(say("adopt the standard first"))
    pack = row["content"]
    bodies = {d["id"]: d["text"] for d in docs}
    changes = result.get("changes") if isinstance(result.get("changes"), list) else []
    with conn.transaction():
        p = conn.execute("insert into qms_setup_proposals (standard, documents, created_by, ai_run, summary) values "
                         "(%s, %s, %s, %s, %s) returning *",
                         (standard, Json([{k: d[k] for k in ("id", "name", "revision", "status")} for d in docs]),
                          email, ai_run, str(result.get("summary") or "")[:2000])).fetchone()
        for seq, raw in enumerate(changes[:MAX_ITEMS], 1):
            item = raw if isinstance(raw, dict) else {}
            doc = item.get("document_id") if type(item.get("document_id")) is int else None
            quote = str(item.get("quote") or "").strip()[:1000]
            try:
                ch = clean(pack, item.get("change"))
                found = check(conn, standard, pack, ch, doc, quote, bodies.get(doc))
            except (SetupError, TypeError, ValueError) as exc:
                ch = {k: str(v)[:200] for k, v in item["change"].items()} if isinstance(item.get("change"), dict) \
                    else {}
                found = {"verified": doc in bodies and WP.quoted(quote, bodies[doc]), "problems": [str(exc)],
                         "already": False}
            conn.execute("insert into qms_setup_items (proposal_id, seq, change, document_id, quote, why, verified, "
                         "problems, already) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                         (p["id"], seq, Json(ch), doc if doc in bodies else None, quote,
                          str(item.get("why") or "")[:1000], found["verified"], Json(found["problems"]),
                          found["already"]))
    return p


def _iso(r: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}


def acceptable(it: dict) -> bool:
    return it["decision"] == "open" and it["verified"] and not it["problems"] and not it["already"]


def view(conn, pid: int) -> dict:
    p = conn.execute("select * from qms_setup_proposals where id = %s", (pid,)).fetchone()
    if p is None:
        raise KeyError(pid)
    row = QMS.enabled(conn, p["standard"])
    pack = row["content"] if row else QMS.load(p["standard"])
    docs = {d["id"]: d for d in p["documents"]}
    items = conn.execute("select * from qms_setup_items where proposal_id = %s order by seq", (pid,)).fetchall()
    return {**_iso(p), "items": [{**_iso(i), "text": describe(pack, i["change"]),
                                  "document": docs.get(i["document_id"]),
                                  "acceptable": acceptable(i)} for i in items]}


def listing(conn, standard: str) -> list[dict]:
    rows = conn.execute("select p.id, p.created_at, p.created_by, p.summary, p.documents, count(i.id) as changes, "
                        "count(i.id) filter (where i.decision = 'accepted') as accepted from qms_setup_proposals p "
                        "left join qms_setup_items i on i.proposal_id = p.id where p.standard = %s group by p.id "
                        "order by p.id desc limit 20", (standard,)).fetchall()
    return [_iso(r) for r in rows]


def decide(conn, user: dict, iid: int, accept: bool, *, password: str = "", note: str = "",
           today: dt.date, tz: str = "UTC") -> dict:
    """Accept (make the change, as a person would by hand) or reject one proposed change. The item is locked while
    the change is made, so it is decided and made once."""
    if accept:
        it = conn.execute("select i.*, p.standard from qms_setup_items i join qms_setup_proposals p on "
                          "p.id = i.proposal_id where i.id = %s", (iid,)).fetchone()
        if it is not None and acceptable(it) and it["change"].get("kind") == "applies":
            Q.check_signer(conn, user, password)       # before the transaction: a failed attempt stays recorded
    with conn.transaction():
        it = conn.execute("select i.*, p.standard from qms_setup_items i join qms_setup_proposals p on "
                          "p.id = i.proposal_id where i.id = %s for update of i", (iid,)).fetchone()
        if it is None:
            raise KeyError(iid)
        if it["decision"] != "open":
            raise SetupError(say("this change was already {decision} by {decided_by}",
                                 decision=it['decision'], decided_by=it['decided_by']))
        if accept:
            if not acceptable(it):
                raise SetupError(say("only a change whose quote was found and that passes the checks can be accepted"))
            ch, std = it["change"], it["standard"]
            if ch["kind"] == "setting":
                QMS.set_setting(conn, user["email"], std, ch["key"], ch["value"], today, tz)
            elif ch["kind"] == "applies":
                QMS.declare(conn, user, std, ch["control"], ch["applies"], ch["reason"], password, today, tz)
            else:
                QMS.link(conn, user["email"], std, ch["control"], it["document_id"], True, today,
                         f"proposed from the procedure: \"{it['quote'][:300]}\"", tz)
        return conn.execute("update qms_setup_items set decision = %s, decided_by = %s, decided_at = now(), "
                            "decision_note = %s where id = %s returning *",
                            ("accepted" if accept else "rejected", user["email"], note.strip()[:1000] or None,
                             iid)).fetchone()


# ---------------------------------------------------------------- procedures written from the workflow in use

TITLES = {"ncr": ("Control of Nonconforming Product", "nonconformance"),
          "capa": ("Corrective and Preventive Action", "capa")}


def procedure_text(conn, kind: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """The procedure for a kind of record, written from the enabled workflow: (title, [(heading, paragraphs)])."""
    v = W.ensure(conn, kind)
    cfg = W.view(v["config"])
    title = TITLES[kind][0]
    label = {s: x.get("label", s) for s, x in cfg["states"].items()}
    open_states = [label[s] for s, x in cfg["states"].items() if not x.get("final")]
    steps = []
    for name, st in cfg["steps"].items():
        bits = [f"{st.get('label') or name} (from {', '.join(label[s] for s in st['from'])}"
                + (f" to {label[st['to']]})" if st.get("to") else ")")]
        bits.append("Done by: " + ", ".join(r.replace("_", " ") for r in st["who"]) + ".")
        if st["needs"]:
            bits.append("Needs: " + ", ".join(st["needs"]) + ".")
        if st.get("reason"):
            bits.append("A reason is recorded.")
        if st.get("sign"):
            bits.append(f"Signed with the person's password: \"{st['sign']}\".")
        if st["not_by_text"]:
            bits.append("Not done by " + " or ".join(st["not_by_text"]) + ".")
        own = [f["label"] for f in cfg["fields"].values() if name in (f.get("required_at") or [])]
        if own:
            bits.append("Recorded first: " + ", ".join(own) + ".")
        appr = [f"{a['label']} (signed by {' or '.join(a['roles'])}"
                + "".join(f", when {k} is {' or '.join(x)}" for k, x in (a.get("when") or {}).items()) + ")"
                for a in cfg["approvals"] if a["before"] == name]
        if appr:
            bits.append("Approved first: " + "; ".join(appr) + ".")
        steps.append(" ".join(bits))
    rules = []
    for sev in (cfg.get("rules") or {}).get("capa_closed_before_close") or []:
        rules.append(f"A {sev} nonconformance is closed only after its corrective action is closed.")
    for sev in (cfg.get("rules") or {}).get("eight_d_before_close") or []:
        rules.append(f"A {sev} nonconformance is closed only after its 8D report is complete.")
    if (cfg.get("rules") or {}).get("one_open_capa_per_ncr"):
        rules.append("A nonconformance has at most one open corrective action at a time.")
    num = cfg["numbering"]
    name_of = cfg.get("label") or kind
    sections = [
        ("1. Purpose", [f"To set out how {name_of.lower()}s are recorded, decided and closed, as WenQuest Ops "
                        "carries them out. This procedure is written from the workflow in use; when the workflow "
                        "changes, it is written again."]),
        ("2. Scope", ["Every " + name_of.lower() + " recorded in WenQuest Ops."]),
        ("3. Records", [f"Each is numbered {num['prefix']}-{'0' * (int(num['digits']) - 1)}1 onwards and moves "
                        f"through: {', '.join(open_states)}, then "
                        + " or ".join(label[s] for s, x in cfg["states"].items() if x.get("final")) + ".",
                        "Every step is logged with who did it and when; signatures and the log cannot be changed "
                        "or deleted; a closed or cancelled record is locked."]),
        ("4. Steps", steps),
    ]
    if cfg["fields"]:
        sections.append(("5. Information the company records", [
            f"{f['label']} ({f['type']})" for f in cfg["fields"].values()]))
    if rules:
        sections.append((f"{len(sections) + 1}. Rules", rules))
    sections.append((f"{len(sections) + 1}. Source", [f"{name_of} workflow version {v['version']}, enabled by "
                                                      f"{v['enabled_by']} on {v['enabled_at']:%Y-%m-%d}, fingerprint "
                                                      f"{v['fingerprint'][:12]}."]))
    return title, sections


def _docx(company: str, title: str, sections: list[tuple[str, list[str]]]) -> bytes:
    import docx as D  # noqa: PLC0415 - python-docx, a hub dependency

    d = D.Document()
    d.sections[0].header.paragraphs[0].text = f"{company} - written by WenQuest Ops from the workflow in use; " \
                                              "not in effect until approved"
    d.add_heading(title, level=1)
    for h, paras in sections:
        d.add_heading(h, level=2)
        for p in paras:
            d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def generate(conn, email: str, kind: str, company: str = "the company") -> dict:
    """Write the procedure for a kind of record into the library, to review and have approved."""
    if kind not in TITLES:
        raise KeyError(kind)
    v = W.ensure(conn, kind)
    source = f"{kind} workflow v{v['version']}"
    title, sections = procedure_text(conn, kind)
    data = _docx(company, title, sections)
    with conn.transaction():
        imp = LIB.new_import(conn, email, f"Written from the {source}")
        doc = LIB.add_file(conn, imp["id"], f"{title} (from {source}).docx", data)
        LIB.extract_one(conn, LIB.get(conn, doc["id"]))
        conn.execute("update documents set generated_from = %s where id = %s", (source, doc["id"]))
        row = LIB.propose(conn, doc["id"], {"doc_type": "procedure", "process": TITLES[kind][1], "title": title,
                                            "revision": f"W{v['version']}", "confidence": "high",
                                            "summary": f"Written by WenQuest Ops from the {source}."}, "generated")
        conn.execute("update doc_imports set status = 'done', engine = 'rules' where id = %s", (imp["id"],))
        LIB.log(conn, doc["id"], email, "written from the workflow", source)
    return row


def generated(conn) -> list[dict]:
    """Procedures written from workflows, and whether the workflow has changed since."""
    current = {k: f"{k} workflow v{W.ensure(conn, k)['version']}" for k in TITLES}
    rows = conn.execute("select id, title, status, generated_from, created_at from documents where generated_from "
                        "is not null and status not in ('rejected', 'obsolete') order by id desc").fetchall()
    return [{**_iso(r), "current": r["generated_from"] == current.get(r["generated_from"].split(" ")[0])}
            for r in rows]
