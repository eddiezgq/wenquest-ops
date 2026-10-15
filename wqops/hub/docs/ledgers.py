"""Ledger imports (ADR-0014 item 10, step 14c): a proposed column mapping for a spreadsheet in the library, its
preview, a person's changes, and the signed import that turns each row into a historical NCR, a corrective action or
an ERPNext supplier draft. Every created record names the file and row it came from; a row is imported once.

The model only proposes the mapping (ledger_ai.py). Here is plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt

from psycopg.types.json import Jsonb

from wqops.hub import drafts as D
from wqops.hub.docs import ledger as LG
from wqops.hub.docs import library as LIB
from wqops.hub.docs import store as F
from wqops.hub.quality import records as Q
from wqops.hub.system import registers as RG

SHEETS = (".xlsx", ".xlsm", ".csv")
PREVIEW = 200

LG.add_registers(RG.specs())             # the quality registers can be brought in from old spreadsheets


class LedgerError(ValueError):
    pass


def dispositions(conn) -> dict[str, str]:
    return {k: v["name"] for k, v in Q.disposition_types(conn).items()}


def is_ledger(doc: dict) -> bool:
    return doc["original_name"].lower().endswith(SHEETS)


def table_of(conn, doc: dict, sheet: str = "", header_row: int = 0) -> LG.Table:
    if not is_ledger(doc):
        raise LedgerError("only Excel (.xlsx) and CSV files can be imported as ledgers")
    if doc.get("duplicate_of"):
        raise LedgerError(f"this file is the same as document {doc['duplicate_of']}; read that one")
    try:
        return LG.table(doc["original_name"], F.get(doc["sha256"]), sheet, header_row)
    except ValueError as exc:
        raise LedgerError(str(exc)) from exc
    except Exception as exc:  # a damaged or mislabelled file: say so instead of failing
        raise LedgerError(f"the spreadsheet could not be read ({type(exc).__name__}); save it again as .xlsx or "
                          ".csv") from exc


def flds(conn, target: str) -> dict[str, LG.Field]:
    if target not in LG.TARGETS:
        raise LedgerError(f"a ledger is one of: {', '.join(LG.TARGETS)}")
    return LG.fields(target, dispositions(conn))


def create(conn, email: str, doc: dict, target: str, t: LG.Table, proposal: dict, engine: str,  # noqa: PLR0917
           ai_run: int | None = None) -> dict:
    checked = LG.check_mapping(target, t, flds(conn, target), proposal)
    notes = checked["notes"] + (("\nNot used: " + "; ".join(checked["dropped"])) if checked["dropped"] else "")
    same = [f"{f} = {m['value']}" for f, m in checked["mapping"].items() if "value" in m]
    if same:
        notes += "\nSet the same for every row (not a column of the ledger; check it): " + ", ".join(same)
    return conn.execute(
        "insert into ledger_imports (document_id, target, sheet, header_row, mapping, values_map, engine, confidence, "
        "notes, ai_run, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
        (doc["id"], target, t.sheet, t.header_row, Jsonb(checked["mapping"]), Jsonb(checked["values"]), engine,
         checked["confidence"], notes.strip()[:2000], ai_run, email)).fetchone()


def get(conn, lid: int) -> dict:
    row = conn.execute("select * from ledger_imports where id = %s", (lid,)).fetchone()
    if row is None:
        raise KeyError(lid)
    return row


def _done_rows(conn, doc_id: int, target: str, sheet: str) -> dict[int, dict]:
    rows = conn.execute("select row_no, outcome, ref from ledger_rows where document_id = %s and target = %s and "
                        "sheet = %s and outcome <> 'skipped'", (doc_id, target, sheet)).fetchall()
    return {r["row_no"]: r for r in rows}


def preview(conn, imp: dict) -> dict:
    doc = LIB.get(conn, imp["document_id"])
    t = table_of(conn, doc, imp["sheet"], imp["header_row"])
    spec = flds(conn, imp["target"])
    rows = LG.rows(t, spec, imp["mapping"], imp["values_map"])
    done = _done_rows(conn, doc["id"], imp["target"], t.sheet)
    for r in rows:
        if r["row"] in done:
            r["done"] = done[r["row"]]["ref"]
    columns = {}
    for f, m in imp["mapping"].items():
        if "column" in m and spec[f].kind == "choice":
            columns[f] = sorted({v[m["column"]] for _, v in t.data() if v.get(m["column"])})
    return {"sheets": t.sheets, "sheet": t.sheet, "header_row": t.header_row, "headers": [h for h in t.headers if h],
            "fields": {k: {"label": v.label, "kind": v.kind, "required": v.required, "choices": list(v.choices)}
                       for k, v in spec.items()},
            "choice_values": columns, "rows": rows[:PREVIEW], "total": len(rows),
            "ready": sum(r["ok"] and "done" not in r for r in rows), "with_problems": sum(bool(r["problems"])
                                                                                         for r in rows),
            "already": sum("done" in r for r in rows), "target_label": LG.TARGETS[imp["target"]]["label"],
            "document": {"id": doc["id"], "name": doc["original_name"], "title": doc["title"]}}


def update(conn, email: str, lid: int, *, mapping: dict, values: dict, sheet: str | None = None,
           header_row: int | None = None) -> dict:
    """A person's mapping replaces the proposal (only what fits the table is kept)."""
    imp = get(conn, lid)
    if imp["status"] != "proposed":
        raise LedgerError("this ledger is already imported")
    doc = LIB.get(conn, imp["document_id"])
    t = table_of(conn, doc, imp["sheet"] if sheet is None else sheet,
                 imp["header_row"] if header_row is None and sheet is None else header_row or 0)
    if not mapping and (t.sheet != imp["sheet"] or t.header_row != imp["header_row"]):
        proposal = LG.rules_mapping(imp["target"], t, flds(conn, imp["target"]))   # new columns: match them again
        mapping, values = proposal["mapping"], proposal["values"]
    checked = LG.check_mapping(imp["target"], t, flds(conn, imp["target"]),
                               {"mapping": mapping, "values": values, "confidence": imp["confidence"]})
    if checked["dropped"]:
        raise LedgerError("does not fit the table: " + "; ".join(checked["dropped"][:5]))
    return conn.execute("update ledger_imports set sheet = %s, header_row = %s, mapping = %s, values_map = %s, "
                        "engine = 'person' where id = %s returning *",
                        (t.sheet, t.header_row, Jsonb(checked["mapping"]), Jsonb(checked["values"]), lid)).fetchone()


# ---------------------------------------------------------------- import

def _person(conn, v: str | None) -> str | None:
    if not v:
        return None
    r = conn.execute("select email from users where lower(email) = lower(%s) or lower(name) = lower(%s) limit 1",
                     (v.strip(), v.strip())).fetchone()
    return r["email"] if r else None


def _at(d: str | None) -> dt.datetime | None:
    return dt.datetime.combine(dt.date.fromisoformat(d), dt.time(12), tzinfo=dt.UTC) if d else None


def _source(doc: dict, n: int) -> str:
    return f"{doc['original_name']} row {n}"


def _said(raw: dict, v: dict, f: str, label: str, then: str) -> str | None:
    """A note for a field the record leaves unknown: what the ledger said, or that it said nothing."""
    if f in v:
        return None
    if raw.get(f):
        return f"{label} in the ledger: {raw[f]!r}, not matched{then}"
    return f"{label} not given in the ledger{then}"


def _dropped_close(v: dict, status: str) -> str | None:
    return f"Closing date in the ledger: {v['closed_on']} (kept only for closed records)" \
        if v.get("closed_on") and status != "closed" else None


def _ncr(conn, email: str, doc: dict, n: int, v: dict, raw: dict) -> tuple[str, str, str]:  # noqa: PLR0917
    if v.get("external_no") and conn.execute(
            "select 1 from ncr_records where external_no = %s and reported_on is not distinct from %s",
            (v["external_no"], v.get("reported_on"))).fetchone():
        return "skipped", "", f"NCR {v['external_no']} of {v.get('reported_on') or 'no date'} was imported before"
    desc = v["description"]
    notes = []
    owner = _person(conn, v.get("owner"))
    if v.get("owner") and not owner:
        notes.append(f"Owner in the ledger: {v['owner']}")
    status = v.get("status") or "open"
    notes += [x for x in (_said(raw, v, "severity", "Severity", "; set it before closing"),
                          _said(raw, v, "status", "Status", "; imported as open"),
                          _said(raw, v, "disposition", "Disposition", "") if raw.get("disposition") else None,
                          _dropped_close(v, status)) if x]
    title = v.get("title") or desc.splitlines()[0][:80]
    full = desc + ("\n\n" + ". ".join(notes) + "." if notes else "")
    name, wf = Q.new_name(conn, "ncr")
    row = conn.execute(
        "insert into ncr_records (name, title, description, item_code, supplier, quantity, severity, owner, "
        "containment, disposition, status, closed_at, cancel_reason, created_by, external_no, reported_on, "
        "source_doc, source_row, workflow_version) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
        "%s, %s, %s, %s, %s) returning *",
        (name, title, full, v.get("item_code"), v.get("supplier"), v.get("quantity"), v.get("severity"),
         owner, v.get("containment"), v.get("disposition"), status, _at(v.get("closed_on")) if status == "closed"
         else None, "cancelled in the ledger" if status == "cancelled" else None, email, v.get("external_no"),
         v.get("reported_on"), doc["id"], n, wf)).fetchone()
    Q.log(conn, "ncr", row["id"], email, "imported", f"from {_source(doc, n)}")
    if status == "closed":
        Q.log(conn, "ncr", row["id"], None, "closed before WenQuest Ops",
              f"on {v['closed_on']}" if v.get("closed_on") else "date not in the ledger")
    return "imported", name, ""


def _capa(conn, email: str, doc: dict, n: int, v: dict, raw: dict) -> tuple[str, str, str]:  # noqa: PLR0917
    if v.get("external_no") and conn.execute(
            "select 1 from capas where external_no = %s and reported_on is not distinct from %s",
            (v["external_no"], v.get("reported_on"))).fetchone():
        return "skipped", "", f"CAPA {v['external_no']} of {v.get('reported_on') or 'no date'} was imported before"
    notes = []
    owner = _person(conn, v.get("owner"))
    if v.get("owner") and not owner:
        notes.append(f"Owner in the ledger: {v['owner']}")
    status = v.get("status") or "draft"
    said = _said(raw, v, "status", "Status", "; starts as a draft")
    if said:
        notes.append(said)
    elif status not in ("closed", "cancelled", "draft"):
        notes.append(f"Status in the ledger: {raw.get('status') or status}; continue it here from the start")
        status = "draft"
    if (x := _dropped_close(v, status)):
        notes.append(x)
    if v.get("action"):
        notes.append(f"Action in the ledger: {v['action']}")
    ncr = None
    if v.get("ncr"):
        found = conn.execute("select id, name from ncr_records where external_no = %s or name = %s order by id",
                             (v["ncr"], v["ncr"])).fetchall()
        if len(found) == 1:
            ncr = found[0]
        else:                                       # none, or several with that number: no link is guessed
            notes.append(f"Related NCR in the ledger: {v['ncr']}, " + ("not found here" if not found else
                         "more than one NCR has that number (" + ", ".join(f["name"] for f in found) + ")"))
    desc = (v.get("description") or "") + ("\n\n" + ". ".join(notes) + "." if notes else "")
    name, wf = Q.new_name(conn, "capa")
    row = conn.execute(
        "insert into capas (name, kind, title, description, owner, risk, root_cause, containment, status, closed_at, "
        "cancel_reason, created_by, external_no, reported_on, source_doc, source_row, workflow_version) values (%s, "
        "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
        (name, v["kind"], v["title"], desc.strip(), owner, v.get("risk"), v.get("root_cause"), v.get("containment"),
         status, _at(v.get("closed_on")) if status == "closed" else None,
         "cancelled in the ledger" if status == "cancelled" else None, email, v.get("external_no"),
         v.get("reported_on"), doc["id"], n, wf)).fetchone()
    if ncr:
        conn.execute("insert into capa_ncrs (capa_id, ncr_id) values (%s, %s) on conflict do nothing",
                     (row["id"], ncr["id"]))
    Q.log(conn, "capa", row["id"], email, "imported", f"from {_source(doc, n)}")
    if status == "closed":
        Q.log(conn, "capa", row["id"], None, "closed before WenQuest Ops",
              f"on {v['closed_on']}" if v.get("closed_on") else "date not in the ledger")
    return "imported", name, ""


def _supplier(conn, user: dict, doc: dict, n: int, v: dict) -> tuple[str, str, str]:
    name = v["supplier_name"].strip()
    if conn.execute("select 1 from ont_objects where type = 'Supplier' and not deleted and (lower(key) = lower(%s) "
                    "or lower(title) = lower(%s))", (name, name)).fetchone():
        return "skipped", "", f"{name} is already in ERPNext"
    if conn.execute("select 1 from erp_drafts where doctype = 'Supplier' and status in ('pending', 'confirming', "
                    "'failed') and lower(payload->>'supplier_name') = lower(%s)", (name,)).fetchone():
        return "skipped", "", f"a draft for {name} is already waiting"
    details = [f"{label}: {v[k]}" for k, label in (("supplies", "Supplies"), ("approval", "Approval status"),
                                                    ("approved_on", "Approved on"), ("certificate", "Certificate"),
                                                    ("country", "Country")) if v.get(k)]
    details.append(f"From {_source(doc, n)}")
    payload = {"supplier_name": name, "supplier_details": "\n".join(details)}
    if v.get("website"):
        payload["website"] = v["website"]
    d = D.propose(conn, user, "Supplier", payload, summary=f"New supplier {name} from the supplier list "
                                                            f"({_source(doc, n)})")
    return "drafted", f"draft {d['id']}", ""


def _register(conn, email: str, name: str, doc: dict, n: int, v: dict) -> tuple[str, str, str]:  # noqa: PLR0917
    """One row into a quality register (ADR-0016, 16b)."""
    vals = {f: (x.isoformat() if isinstance(x, dt.date) else x) for f, x in v.items()}
    try:
        row = RG.create(conn, email, name, vals, source_doc=doc["id"], source_row=n, note=_source(doc, n))
    except RG.RegisterError as exc:
        return "skipped", "", str(exc)
    return "imported", f"entry {row['id']}", ""


def run_import(conn, user: dict, lid: int, password: str) -> dict:
    """Signed import of every ready row not imported before. The import itself is signed with the person's
    password; each row's outcome is recorded (append-only)."""
    imp = get(conn, lid)
    if imp["status"] != "proposed":
        raise LedgerError("this ledger is already imported")
    doc = LIB.get(conn, imp["document_id"])
    t = table_of(conn, doc, imp["sheet"], imp["header_row"])
    rows = LG.rows(t, flds(conn, imp["target"]), imp["mapping"], imp["values_map"])
    Q.check_signer(conn, user, password)              # before the transaction: a failed attempt stays recorded
    counts = {"imported": 0, "drafted": 0, "skipped": 0}
    with conn.transaction():
        # one import of a document at a time: a second waits here and then sees the rows the first brought in
        conn.execute("select id from documents where id = %s for update", (doc["id"],))
        if conn.execute("select status from ledger_imports where id = %s for update", (lid,)).fetchone()["status"] \
                != "proposed":
            raise LedgerError("this ledger is already imported")
        done = _done_rows(conn, doc["id"], imp["target"], t.sheet)
        for r in rows:
            if r["row"] in done:
                outcome, ref, note = "skipped", "", f"imported before as {done[r['row']]['ref']}"
            elif not r["ok"]:
                outcome, ref, note = "skipped", "", "; ".join(r["problems"])
            elif imp["target"] == "ncr":
                outcome, ref, note = _ncr(conn, user["email"], doc, r["row"], r["values"], r["raw"])
            elif imp["target"] == "capa":
                outcome, ref, note = _capa(conn, user["email"], doc, r["row"], r["values"], r["raw"])
            elif imp["target"] == "supplier":
                outcome, ref, note = _supplier(conn, user, doc, r["row"], r["values"])
            else:
                outcome, ref, note = _register(conn, user["email"], imp["target"][4:], doc, r["row"], r["values"])
            if outcome != "skipped" and r["problems"]:
                note = "; ".join(r["problems"])
            counts[outcome] += 1
            conn.execute("insert into ledger_rows (import_id, document_id, target, sheet, row_no, outcome, ref, note) "
                         "values (%s, %s, %s, %s, %s, %s, %s, %s)", (lid, doc["id"], imp["target"], t.sheet, r["row"],
                                                                     outcome, ref or None, note[:1000]))
        Q._sign(conn, user, "Ledger rows imported", "ledger", lid,
                f"{doc['original_name']}: {counts['imported'] + counts['drafted']} rows")
        out = conn.execute("update ledger_imports set status = 'imported', imported_by = %s, imported_at = now(), "
                           "result = %s where id = %s returning *", (user["email"], Jsonb(counts), lid)).fetchone()
        LIB.log(conn, doc["id"], user["email"], "ledger imported",
                f"{LG.TARGETS[imp['target']]['label']}: {counts['imported']} imported, {counts['drafted']} drafted, "
                f"{counts['skipped']} skipped")
    return out


def outcomes(conn, lid: int) -> list[dict]:
    return conn.execute("select row_no, outcome, ref, note from ledger_rows where import_id = %s order by row_no",
                        (lid,)).fetchall()
