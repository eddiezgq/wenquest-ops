"""Writing another system's rows into ERPNext (ADR-0020, 20a), after a person checked the mapping and the preview and
signed. Items, customers and suppliers are created; opening stock (one Stock Reconciliation, purpose Opening Stock)
and open orders are created as drafts in ERPNext for a person to check and submit there, unless the person chose to
submit them at once when signing.

Every row's outcome is kept (ledger_rows) as soon as ERPNext answers, so an import cut off half way goes on where it
stopped when started again: rows already brought in are skipped. A row ERPNext refuses is skipped with its reason and
can be tried again. Nothing here decides anything about quality; it is an installation tool used through the UI.
"""

from __future__ import annotations

import datetime as dt

import httpx
from psycopg.types.json import Jsonb

from wqops.erp import ErpClient, ErpError
from wqops.hub.docs import erp_rows as ER
from wqops.hub.docs import ledger as LG
from wqops.hub.docs import ledgers as LS
from wqops.hub.docs import library as LIB
from wqops.hub.quality import records as Q
from wqops.i18n import say

MASTERS = {"erp_item": "Item", "erp_customer": "Customer", "erp_supplier": "Supplier"}


class ErpImportError(LS.LedgerError):
    pass


def _record(conn, lid: int, doc: dict, imp: dict, sheet: str, row: int, outcome: str, ref: str, note: str) -> None:  # noqa: PLR0917
    conn.execute("insert into ledger_rows (import_id, document_id, target, sheet, row_no, outcome, ref, note) values "
                 "(%s, %s, %s, %s, %s, %s, %s, %s)", (lid, doc["id"], imp["target"], sheet, row, outcome, ref or None,
                                                      note[:1000]))


def _master(target: str, v: dict) -> dict:
    doc = {"doctype": MASTERS[target], **{k: x for k, x in v.items() if k != "is_stock_item"}}
    if target == "erp_item":
        if "is_stock_item" in v:
            doc["is_stock_item"] = 1 if v["is_stock_item"] == "yes" else 0
        doc.setdefault("item_name", v["item_code"])
    return doc


def _order(target: str, lines: list[dict], company: str) -> dict:
    v = lines[0]["values"]
    due = "delivery_date" if target == "erp_sales_order" else "schedule_date"
    items = []
    for r in lines:
        x = r["values"]
        line = {"item_code": r["erp"]["item_code"], "qty": x["qty"], due: x[due]}
        if "rate" in x:
            line["rate"] = x["rate"]
        items.append(line)
    party = "customer" if target == "erp_sales_order" else "supplier"
    return {"doctype": "Sales Order" if target == "erp_sales_order" else "Purchase Order",
            party: lines[0]["erp"][party], due: v[due], "company": company,
            "transaction_date": v["transaction_date"], "items": items}


def _stock(lines: list[dict], company: str, today: dt.date, account: str) -> dict:
    items = []
    for r in lines:
        x = r["values"]
        line = {"item_code": r["erp"]["item_code"], "warehouse": r["erp"]["warehouse"], "qty": x["qty"]}
        if "valuation_rate" in x:
            line["valuation_rate"] = x["valuation_rate"]
        if x.get("batch_no"):
            line.update(batch_no=x["batch_no"], use_serial_batch_fields=1)
        items.append(line)
    return {"doctype": "Stock Reconciliation", "purpose": "Opening Stock", "company": company,
            "posting_date": today.isoformat(), "set_posting_time": 1, "expense_account": account, "items": items}


def opening_account(erp: ErpClient, company: str) -> str:
    """The company's temporary opening account, which ERPNext needs for opening stock (an asset or liability)."""
    rows = erp.find("Account", {"account_type": "Temporary", "company": company, "is_group": 0})
    if not rows:
        raise ErpImportError(say("ERPNext has no Temporary account for {company} (normally 'Temporary Opening'); add "
                                 "it in ERPNext's chart of accounts first",
                                 company=company))
    return rows[0]["name"]


def _take(conn, target: str, key: str | None, lid: int, row: int) -> bool:
    """Take the key before ERPNext is asked; False if another import has it (the record is not doubled)."""
    if key is None:
        return True
    return conn.execute("insert into erp_import_keys (target, key, import_id, row_no) values (%s, %s, %s, %s) "
                        "on conflict do nothing returning key", (target, key, lid, row)).fetchone() is not None


def run(conn, erp: ErpClient, user: dict, lid: int, password: str, *, company: str, today: dt.date,
        submit: bool = False, seen: str | None = None) -> dict:
    """Signed: write every ready row of the import into ERPNext and record what happened to each. ``seen``: the
    mapping the signer looked at (its fingerprint); a mapping changed since is not imported."""
    imp = LS.get(conn, lid)
    target = imp["target"]
    if not target.startswith("erp_"):
        raise ErpImportError(say("this import is not for ERPNext"))
    if seen != LS.mapping_print(imp):
        raise ErpImportError(say("the mapping changed since you looked at it: look at the rows again, then sign"))
    Q.check_signer(conn, user, password)              # before anything is written: a failed attempt stays recorded
    account = opening_account(erp, company) if target == "erp_opening_stock" else ""
    lock = f"wqo-erp-import:{target}"
    conn.execute("select pg_advisory_lock(hashtext(%s))", (lock,))   # one import of a kind at a time
    try:
        return _run(conn, erp, user, imp, company=company, today=today, submit=submit, account=account)
    finally:
        conn.execute("select pg_advisory_unlock(hashtext(%s))", (lock,))


def _run(conn, erp, user, imp, *, company, today, submit, account):  # noqa: PLR0912, PLR0915 - one import
    lid, target = imp["id"], imp["target"]
    with conn.transaction():                          # claim it: a second run of the same import stops here
        if conn.execute("select status from ledger_imports where id = %s for update", (lid,)).fetchone()["status"] \
                != "proposed":
            raise ErpImportError(say("this import has been run; start a new one on the same file to bring in the rest"))
        doc = LIB.get(conn, imp["document_id"])
        conn.execute("update ledger_imports set status = 'imported', imported_by = %s, imported_at = now(), "
                     "submit = %s where id = %s", (user["email"], submit, lid))
        Q._sign(conn, user, "Rows imported into ERPNext", "ledger", lid,
                f"{doc['original_name']}: {LG.TARGETS[target]['label']}")
    t = LS.table_of(conn, doc, imp["sheet"], imp["header_row"])
    rows = ER.annotate(conn, target, LG.rows(t, LS.flds(conn, target), imp["mapping"], imp["values_map"]))
    done = LS._done_rows(conn, doc["id"], target, t.sheet)
    counts = {"imported": 0, "drafted": 0, "skipped": 0}

    def skip(r, why):
        counts["skipped"] += 1
        _record(conn, lid, doc, imp, t.sheet, r["row"], "skipped", "", why)

    try:
        ready = []
        for r in rows:
            why = (f"imported before as {done[r['row']]['ref']}" if r["row"] in done else r.get("exists")
                   or (None if r["ok"] else "; ".join(r["problems"])))
            if why:
                skip(r, why)
            else:
                ready.append(r)
        if target in MASTERS:
            units = [[r] for r in ready]
        elif target == "erp_opening_stock":
            units = [ready] if ready else []
        else:
            groups: dict[tuple, list[dict]] = {}
            for r in rows:
                if r["row"] not in done:
                    groups.setdefault(ER.group_key(r), []).append(r)
            ok = {id(r) for r in ready}
            units = []
            for g, lines in groups.items():
                mine = [r for r in lines if id(r) in ok]
                if mine and len(mine) == len(lines):
                    units.append(mine)
                else:                                 # part of an order cannot come in: none of it does
                    for r in mine:
                        skip(r, f"another line of order {ER.label(g)} cannot be imported")
        for unit in units:
            if target == "erp_opening_stock":         # each item in a warehouse once, ever
                taken = [r for r in unit if _take(conn, target, ER.key_of(target, r), lid, r["row"])]
                for r in unit:
                    if r not in taken:
                        skip(r, "imported by another import meanwhile")
                unit = taken                          # noqa: PLW2901 - the lines still to bring in
                if not unit:
                    continue
                keys = [ER.key_of(target, r) for r in unit]
            else:
                k = ER.key_of(target, unit[0])
                if not _take(conn, target, k, lid, unit[0]["row"]):
                    for r in unit:
                        skip(r, "imported by another import meanwhile")
                    continue
                keys = [k] if k else []
            if target in MASTERS:
                payload = _master(target, unit[0]["values"])
            elif target == "erp_opening_stock":
                payload = _stock(unit, company, today, account)
            else:
                payload = _order(target, unit, company)
            if target not in MASTERS and submit:
                payload["docstatus"] = 1
            try:
                out = erp.insert(payload)
                name = out["name"]
            except (ErpError, httpx.ConnectError) as exc:    # refused, or never reached: nothing was created
                conn.execute("delete from erp_import_keys where target = %s and key = any(%s) and ref is null",
                             (target, keys))
                for r in unit:
                    skip(r, f"ERPNext refused it: {exc}"[:900])
                continue
            except Exception as exc:  # unknown whether ERPNext created it: its key stays taken
                for r in unit:
                    skip(r, f"no clear answer from ERPNext ({type(exc).__name__}): check ERPNext before importing "
                            "this row again")
                continue
            conn.execute("update erp_import_keys set ref = %s where target = %s and key = any(%s)",
                         (f"{payload['doctype']}:{name}", target, keys))
            outcome = "imported" if target in MASTERS or submit else "drafted"
            for r in unit:
                counts[outcome] += 1
                _record(conn, lid, doc, imp, t.sheet, r["row"], outcome, f"{payload['doctype']}:{name}",
                        "" if outcome == "imported" else "a draft in ERPNext: check and submit it there")
    finally:
        conn.execute("update ledger_imports set result = %s where id = %s", (Jsonb(counts), lid))
        LIB.log(conn, doc["id"], user["email"], "imported into ERPNext",
                f"{LG.TARGETS[target]['label']}: {counts['imported']} created, {counts['drafted']} drafts, "
                f"{counts['skipped']} skipped")
    return LS.get(conn, lid)
