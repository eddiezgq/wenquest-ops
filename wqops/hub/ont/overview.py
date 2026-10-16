"""The company overview (ADR-0018): seven panels with a light each, the chain from purchase order to cash, weekly
curves and what waits for people. Every number is counted here from ERPNext's synced objects and WenQuest Ops'
records; nothing is estimated and no AI is involved. With no data a number is None ("unknown").

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt
from contextvars import ContextVar

from wqops.hub import permissions as P
from wqops.hub.ont import metrics as M
from wqops.hub.ont import overview_rules as R

TZ: ContextVar[str] = ContextVar("overview_tz", default="UTC")   # the company's time zone for this request
ATTENTION_DAYS = 2      # a lot or a receipt waiting longer than this is "stuck" on the chain
OPEN_PO = ("To Receive and Bill", "To Receive")   # ERPNext statuses with goods still to come


class _Rows(list):
    def fetchall(self):
        return self

    def fetchone(self):
        return self[0] if self else None


class Memo:
    """One request reads each set of ERPNext objects once: the same query on the objects and links is answered from
    memory (the panels and the weekly curves ask for them many times)."""

    def __init__(self, conn):
        self.conn, self.memo = conn, {}

    def execute(self, sql, params=None):
        if "ont_objects" not in sql and "ont_links" not in sql:
            return self.conn.execute(sql, params)
        key = (sql, tuple(params or ()))
        if key not in self.memo:
            self.memo[key] = _Rows(self.conn.execute(sql, params).fetchall())
        return self.memo[key]


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _docs(conn, type_: str, returns: bool = False) -> list[dict]:
    """Submitted ERPNext documents of a type (not cancelled; returns and credit notes only when asked for)."""
    return [o for o in M._objs(conn, type_)
            if M._submitted(o["props"]) and (returns or not o["props"].get("is_return"))]


def _party(conn, src: str, kind: str) -> dict[str, str]:
    return {r["src_key"]: r["dst_key"] for r in conn.execute(
        "select src_key, dst_key from ont_links where src_type = %s and type = %s", (src, kind))}


def _figure(label: str, value, unit: str = "", link: str | None = None, note: str = "") -> dict:
    return {"label": label, "value": value, "unit": unit, "link": link, "note": note}


def _panel(key: str, rules: dict, light_value, figures, series=None, lists=None) -> dict:  # noqa: PLR0917
    rule = rules[key]
    return {"key": key, "label": R.LABELS[key],
            "light": {"value": light_value, "unit": rule["unit"], "what": rule["what"], "color": R.light(light_value,
                                                                                                         rule),
                      "green": rule["green"], "amber": rule["amber"], "better": rule["better"],
                      "default": rule["default"]},
            "figures": figures, "series": series or {}, "lists": lists or {}}


# ---------------------------------------------------------------- the seven panels

def sales(conn, as_of: dt.date, weeks: int, rules: dict) -> dict:
    orders = _docs(conn, "SalesOrder")
    cust = _party(conn, "SalesOrder", "customer")
    series = R.by_week(((M._d(o["props"].get("transaction_date")), _num(o["props"].get("grand_total")))
                        for o in orders), as_of, weeks)
    since = as_of - dt.timedelta(days=29)
    top: dict[str, float] = {}
    for o in orders:
        d = M._d(o["props"].get("transaction_date"))
        if d and since <= d <= as_of:
            name = o["props"].get("customer_name") or cust.get(o["key"]) or "unknown customer"
            top[name] = top.get(name, 0) + _num(o["props"].get("grand_total"))
    month = sum(top.values()) if orders else None
    # the light always reads the last 8 weeks, and only once there are 8 weeks of orders to compare with
    first = min((d for d in (M._d(o["props"].get("transaction_date")) for o in orders) if d), default=None)
    eight = series if weeks == 8 else R.by_week(((M._d(o["props"].get("transaction_date")),
                                                  _num(o["props"].get("grand_total"))) for o in orders), as_of, 8)
    enough = first is not None and first <= as_of - dt.timedelta(days=55)
    return _panel("sales", rules, R.vs_average(eight) if enough else None, [
        _figure("Orders, last 30 days", round(month, 2) if month is not None else None, "currency", "/objects"),
        _figure("Orders this week", series[-1]["count"] if orders else None, "orders"),
        _figure("Against last week", R.change(series), "%")],
        {"orders": {"label": "Order value by week", "unit": "currency", "points": series}},
        {"customers": [{"label": k, "value": round(v, 2), "unit": "currency"}
                       for k, v in sorted(top.items(), key=lambda x: -x[1])[:5]]})


def late_orders(conn, as_of: dt.date) -> list[dict]:
    """Open sales orders past their delivery date, most late first."""
    out = []
    for o in _docs(conn, "SalesOrder"):
        due = M._d(o["props"].get("delivery_date"))
        if o["props"].get("status") in M.OPEN_SO and due and due < as_of:
            out.append({"label": o["title"], "value": (as_of - due).days, "unit": "days late",
                        "link": f"/o/SalesOrder/{o['key']}"})
    return sorted(out, key=lambda x: -x["value"])


def delivery(conn, as_of: dt.date, weeks: int, rules: dict) -> dict:
    otd = M.on_time_delivery(conn, as_of, 30)
    trend = M.weekly(conn, "on_time_delivery", as_of, weeks)
    late = late_orders(conn, as_of)
    return _panel("delivery", rules, otd["value"], [
        _figure("On-time delivery, 30 days", otd["value"], "%", "/"),
        _figure("Delivered late, 30 days", len(otd.get("late", [])), "orders"),
        _figure("Open orders past their date", len(late), "orders")],
        {"on_time": {"label": "On-time delivery by week", "unit": "%", "points": trend}},
        {"late": late[:6]})


def _inventory_by_week(conn, as_of: dt.date, weeks: int) -> list[dict]:
    """The stock value at the end of each week: the ledger's value changes up to that day."""
    moves = sorted((d, _num(o["props"].get("stock_value_difference"))) for o in M._objs(conn, "StockMove")
                   if not o["props"].get("is_cancelled") and (d := M._d(o["props"].get("posting_date"))))
    if not moves:
        return [{"week_ending": str(e), "value": None} for e in R.week_ends(as_of, weeks)]
    out, total, i = [], 0.0, 0
    for e in R.week_ends(as_of, weeks):
        while i < len(moves) and moves[i][0] <= e:
            total += moves[i][1]
            i += 1
        out.append({"week_ending": str(e), "value": round(total, 2)})
    return out


def inventory(conn, as_of: dt.date, weeks: int, rules: dict) -> dict:
    short = M.shortages(conn)
    value = M.inventory_value(conn)
    doi = M.days_of_inventory(conn, as_of)
    has_stock = value["value"] is not None
    return _panel("inventory", rules, short["value"] if has_stock else None, [
        _figure("Stock value", value["value"], "currency"),
        _figure("Days of inventory", doi["value"], "days"),
        _figure("Items short", short["value"] if has_stock else None, "items")],
        {"value": {"label": "Stock value by week", "unit": "currency", "points": _inventory_by_week(conn, as_of,
                                                                                                    weeks)}},
        {"short": [{"label": i["title"], "value": i["short"], "unit": "short", "link": f"/o/Item/{i['item']}"}
                   for i in short.get("items", [])[:6]]})


def purchasing(conn, as_of: dt.date, weeks: int, rules: dict) -> dict:
    sot = M.supplier_on_time(conn, as_of, 30)
    trend = M.weekly(conn, "supplier_on_time", as_of, weeks)
    pos = [o for o in _docs(conn, "PurchaseOrder") if o["props"].get("status") in OPEN_PO]
    values = [o["props"].get("open_value") for o in pos]
    open_value = None if any(v is None for v in values) else round(sum(values), 2)
    late = []
    for o in pos:
        due = M._d(o["props"].get("schedule_date"))
        if due and due < as_of:
            late.append({"label": f"{o['key']} {o['props'].get('supplier_name') or ''}".strip(),
                         "value": (as_of - due).days, "unit": "days late", "link": f"/o/PurchaseOrder/{o['key']}"})
    lots = conn.execute("select count(*) filter (where result = 'reject') as rej, count(*) as n from iqc_inspections "
                        "where (signed_at at time zone %(tz)s)::date between %(a)s and %(b)s",
                        {"tz": TZ.get(), "a": as_of - dt.timedelta(days=29), "b": as_of}).fetchone()
    from wqops.hub.quality import iqc as I  # noqa: PLC0415 - incoming inspection reads the ontology too

    waiting = len(I.awaiting(conn)) + conn.execute("select count(*) as n from iqc_inspections where status in "
                                                   "('in_progress', 'judged')").fetchone()["n"]
    return _panel("purchasing", rules, sot["value"], [
        _figure("Received on time, 30 days", sot["value"], "%"),
        _figure("Still to receive", open_value, "currency"),
        _figure("Purchase orders late", len(late), "orders"),
        _figure("Incoming lots waiting", waiting, "lots", "/quality/iqc"),
        _figure("Incoming lots rejected, 30 days", M._pct(lots["rej"], lots["n"]), "%", "/quality/iqc")],
        {"on_time": {"label": "Received on time by week", "unit": "%", "points": trend}},
        {"late": sorted(late, key=lambda x: -x["value"])[:6]})


def production(conn, as_of: dt.date, weeks: int, rules: dict) -> dict:
    since = as_of - dt.timedelta(days=29)
    rel = conn.execute("select (r.decided_at at time zone %(tz)s)::date as d, exists (select 1 from prod_steps s "
                       "where s.record_id = r.id and s.verdict = 'fail') as failed from prod_records r where status = "
                       "'released'",
                       {"tz": TZ.get()}).fetchall()
    month = [r for r in rel if since <= r["d"] <= as_of]
    first_pass = M._pct(sum(not r["failed"] for r in month), len(month))
    st = {r["status"]: r["n"] for r in conn.execute("select status, count(*) as n from prod_records group by status")}
    series = R.by_week(((r["d"], 1) for r in rel), as_of, weeks)
    return _panel("production", rules, first_pass, [
        _figure("Lots in production", st.get("in_production", 0), "lots", "/quality/production"),
        _figure("Waiting for release", st.get("qa_review", 0), "lots", "/quality/production"),
        _figure("Released, 30 days", len(month), "lots"),
        _figure("First-pass yield, 30 days", first_pass, "%")],
        {"released": {"label": "Lots released by week", "unit": "lots", "points": series}})


def _overdue_quality(conn, as_of: dt.date) -> list[dict]:
    out = [{"label": f"CAPA step: {r['text'][:60]}", "value": (as_of - r["due"]).days, "unit": "days late",
            "link": f"/quality/capa/{r['capa_id']}"} for r in conn.execute(
        "select a.capa_id, a.text, a.due from capa_actions a join capas c on c.id = a.capa_id where not a.done and "
        "a.due < %s and c.status not in ('closed', 'cancelled') order by a.due", (as_of,))]
    out += [{"label": f"Complaint {r['name']}: report due", "value": (as_of - r["deadline_on"]).days,
             "unit": "days late", "link": f"/quality/complaints/{r['id']}"} for r in conn.execute(
        "select id, name, deadline_on from complaints where deadline_on < %s and report_ref = '' and status not in "
        "('closed', 'cancelled') order by deadline_on", (as_of,))]
    out += [{"label": f"Calibration of {r['code']}", "value": (as_of - r["next_due"]).days, "unit": "days late",
             "link": f"/quality/gauges/{r['id']}"} for r in conn.execute(
        "select id, code, next_due from gauges where status <> 'retired' and next_due < %s order by next_due",
        (as_of,))]
    return out


def quality(conn, as_of: dt.date, weeks: int, rules: dict) -> dict:
    ncr = M.open_nonconformances(conn, as_of, 30)
    overdue = _overdue_quality(conn, as_of)
    complaints = conn.execute("select count(*) as n from complaints where status not in ('closed', "
                              "'cancelled')").fetchone()["n"]
    ncr_days = conn.execute("select (created_at at time zone %(tz)s)::date as d from ncr_records", {"tz": TZ.get()})
    opened = R.by_week(((r["d"], 1) for r in ncr_days), as_of, weeks)
    iso = []
    for r in conn.execute("select distinct on (p.standard) p.standard, e.counts from qms_packs p join "
                          "qms_evaluations e on e.pack_id = p.id where p.status = 'enabled' order by p.standard, "
                          "e.id desc"):
        iso.append({"standard": r["standard"], **{k: r["counts"].get(k, 0) for k in ("met", "not_met", "unknown",
                                                                                      "not_applicable")}})
    recalls = conn.execute("select count(*) as n from recalls where status = 'open'").fetchone()["n"]
    used = conn.execute("select exists (select 1 from capas) or exists (select 1 from complaints) or exists "
                        "(select 1 from gauges) as y").fetchone()["y"]
    return _panel("quality", rules, len(overdue) if used else None, [
        _figure("Open nonconformances", ncr["value"], "open", "/quality"),
        _figure("Overdue quality actions", len(overdue), "items"),
        _figure("Open complaints", complaints, "open", "/quality/complaints"),
        _figure("Open recalls", recalls, "open", "/quality/recalls")],
        {"ncrs": {"label": "Nonconformances opened by week", "unit": "reports", "points": opened}},
        {"overdue": sorted(overdue, key=lambda x: -x["value"])[:6], "iso": iso})


def finance(conn, as_of: dt.date, weeks: int, rules: dict) -> dict:
    sinv, pinv = _docs(conn, "SalesInvoice", returns=True), _docs(conn, "PurchaseInvoice", returns=True)
    billed = R.by_week(((M._d(o["props"].get("posting_date")), _num(o["props"].get("grand_total"))) for o in sinv),
                       as_of, weeks)
    ar = [(M._d(o["props"].get("due_date")), _num(o["props"].get("outstanding_amount"))) for o in sinv]
    ap = [(M._d(o["props"].get("due_date")), _num(o["props"].get("outstanding_amount"))) for o in pinv]
    ar_total, ap_total = round(sum(v for _, v in ar), 2), round(sum(v for _, v in ap), 2)
    ar_late = round(sum(v for d, v in ar if d and d < as_of), 2)
    share = round(100.0 * ar_late / ar_total, 1) if ar_total else (0.0 if sinv else None)
    cust = _party(conn, "SalesInvoice", "customer")
    late: dict[str, float] = {}
    for o in sinv:
        d, v = M._d(o["props"].get("due_date")), _num(o["props"].get("outstanding_amount"))
        if d and d < as_of and v > 0:
            name = o["props"].get("customer_name") or cust.get(o["key"]) or "unknown customer"
            late[name] = late.get(name, 0) + v
    return _panel("finance", rules, share, [
        _figure("Receivables", ar_total if sinv else None, "currency"),
        _figure("Overdue receivables", ar_late if sinv else None, "currency"),
        _figure("Overdue share", share, "%"),
        _figure("Payables", ap_total if pinv else None, "currency"),
        _figure("Billed, last 4 weeks", round(sum(w["value"] for w in billed[-4:]), 2) if sinv else None,
                "currency")],
        {"billed": {"label": "Billed by week", "unit": "currency", "points": billed},
         "aging": {"label": "Receivables by days past due", "unit": "currency", "points": R.aging(ar, as_of),
                   "kind": "aging"}},
        {"late_customers": [{"label": k, "value": round(v, 2), "unit": "currency"}
                            for k, v in sorted(late.items(), key=lambda x: -x[1])[:5]]})


PANEL_FNS = {"sales": sales, "delivery": delivery, "inventory": inventory, "purchasing": purchasing,
             "production": production, "quality": quality, "finance": finance}


# ---------------------------------------------------------------- the chain from purchase order to cash

def chain(conn, as_of: dt.date, allowed: set[str]) -> list[dict]:
    """Each step from purchase order to payment: how many are there now and how many are stuck."""
    old = as_of - dt.timedelta(days=ATTENTION_DAYS)
    steps = []
    if "purchasing" in allowed:
        pos = [o for o in _docs(conn, "PurchaseOrder") if o["props"].get("status") in OPEN_PO]
        late = [o for o in pos if (M._d(o["props"].get("schedule_date")) or as_of) < as_of]
        steps.append({"key": "po", "label": "Purchase orders", "count": len(pos), "stuck": len(late),
                      "stuck_note": "past their required-by date", "link": "/objects"})
        drafts = [o for o in M._objs(conn, "PurchaseReceipt") if o["props"].get("docstatus") == 0]
        steps.append({"key": "receipt", "label": "Receiving", "count": len(drafts),
                      "stuck": sum(1 for o in drafts if (M._d(o["props"].get("posting_date")) or as_of) < old),
                      "stuck_note": f"waiting over {ATTENTION_DAYS} days", "link": "/objects"})
    if "quality" in allowed:
        from wqops.hub.quality import iqc as I  # noqa: PLC0415

        wait = I.awaiting(conn)
        busy = conn.execute("select count(*) filter (where (created_at at time zone %(tz)s)::date < %(old)s) as stuck, "
                            "count(*) as n from iqc_inspections where status in ('in_progress', 'judged')",
                            {"tz": TZ.get(), "old": old}).fetchone()
        steps.append({"key": "iqc", "label": "Incoming inspection", "count": len(wait) + busy["n"],
                      "stuck": busy["stuck"], "stuck_note": f"open over {ATTENTION_DAYS} days",
                      "link": "/quality/iqc"})
    if "inventory" in allowed:
        short = M.shortages(conn)
        steps.append({"key": "stock", "label": "Stock", "count": M.inventory_value(conn)["value"],
                      "unit": "currency", "stuck": short["value"], "stuck_note": "items short", "link": "/"})
    if "production" in allowed:
        r = conn.execute("select count(*) filter (where status = 'in_production') as wip, count(*) filter (where "
                         "status = 'in_production' and (created_at at time zone %(tz)s)::date < %(old)s) as wip_old, "
                         "count(*) filter (where status = 'qa_review') as rev, count(*) filter (where status = "
                         "'qa_review' and "
                         "(submitted_at at time zone %(tz)s)::date < %(old)s) as rev_old from prod_records",
                         {"tz": TZ.get(), "old": old}).fetchone()
        steps.append({"key": "make", "label": "Production", "count": r["wip"], "stuck": r["wip_old"],
                      "stuck_note": f"started over {ATTENTION_DAYS} days ago", "link": "/quality/production"})
        steps.append({"key": "release", "label": "Release", "count": r["rev"], "stuck": r["rev_old"],
                      "stuck_note": f"waiting over {ATTENTION_DAYS} days", "link": "/quality/production"})
    if "delivery" in allowed:
        open_so = [o for o in _docs(conn, "SalesOrder") if o["props"].get("status") in M.OPEN_SO]
        steps.append({"key": "ship", "label": "Delivery", "count": len(open_so), "stuck": len(late_orders(conn, as_of)),
                      "stuck_note": "past their date", "link": "/"})
    if "finance" in allowed:
        sinv = _docs(conn, "SalesInvoice")
        to_bill = [o for o in _docs(conn, "SalesOrder") if o["props"].get("status") in ("To Bill",
                                                                                        "To Deliver and Bill")]
        steps.append({"key": "bill", "label": "Invoicing", "count": len(to_bill), "stuck": None,
                      "stuck_note": "", "link": "/"})
        unpaid = [o for o in sinv if _num(o["props"].get("outstanding_amount")) > 0]
        steps.append({"key": "cash", "label": "Payment", "count": len(unpaid),
                      "stuck": sum(1 for o in unpaid if (M._d(o["props"].get("due_date")) or as_of) < as_of),
                      "stuck_note": "past due", "link": "/"})
    return steps


def returns(conn, allowed: set[str]) -> list[dict]:
    """What comes back from customers onto the chain: complaints and recalls."""
    if "quality" not in allowed:
        return []
    c = conn.execute("select count(*) as n from complaints where status not in ('closed', 'cancelled')").fetchone()
    r = conn.execute("select count(*) as n from recalls where status = 'open'").fetchone()
    return [{"key": "complaints", "label": "Complaints", "count": c["n"], "link": "/quality/complaints"},
            {"key": "recalls", "label": "Recalls", "count": r["n"], "link": "/quality/recalls"}]


# ---------------------------------------------------------------- what waits for people

def waiting(conn, user: dict, as_of: dt.date) -> list[dict]:
    roles, me = user["roles"], user["email"]
    out = []

    def add(kind: str, label: str, n: int, link: str, urgent: bool = False) -> None:
        if n:
            out.append({"kind": kind, "label": label, "count": n, "link": link, "urgent": urgent})

    add("reading", "Documents for you to read", conn.execute(
        "select count(*) as n from doc_training where email = %s and status = 'pending'", (me,)).fetchone()["n"],
        "/documents/control", urgent=bool(conn.execute(
            "select 1 from doc_training where email = %s and status = 'pending' and due < %s", (me, as_of)).fetchone()))
    if P.allows(roles, "ai:use"):
        add("drafts", "Drafts to confirm or reject", conn.execute(
            "select count(*) as n from erp_drafts where status = 'pending'").fetchone()["n"], "/drafts")
    if P.allows(roles, "quality:view"):
        overdue = _overdue_quality(conn, as_of)
        add("overdue", "Overdue quality actions", len(overdue), "/quality", urgent=True)
    if P.allows(roles, "qms:configure"):
        for kind, label, sql, link in (
            ("iqc", "Incoming lots to release or reject", "select count(*) as n from iqc_inspections where status = "
                                                          "'judged'", "/quality/iqc"),
            ("release", "Production lots to release", "select count(*) as n from prod_records where status = "
                                                       "'qa_review'", "/quality/production"),
            ("changes", "Changes to approve", "select count(*) as n from changes where status = 'submitted'",
             "/quality/changes"),
            ("risk", "Risk files to approve", "select count(*) as n from risk_files where status = 'draft'",
             "/quality/risk"),
            ("calibration", "Calibrations to approve", "select count(*) as n from gauge_calibrations where status = "
                                                       "'draft'", "/quality/gauges")):
            add(kind, label, conn.execute(sql).fetchone()["n"], link)
    return sorted(out, key=lambda x: (not x["urgent"], -x["count"]))


# ---------------------------------------------------------------- all of it

def allowed_panels(roles) -> set[str]:
    return {k for k in R.PANELS if P.allows(roles, R.VIEW[k])}


def build(conn, user: dict, as_of: dt.date, weeks: int, saved: dict | None = None, *, tz: str = "UTC") -> dict:
    TZ.set(tz)
    conn = Memo(conn)
    rules = R.thresholds((saved or {}).get("thresholds"))
    allowed = allowed_panels(user["roles"])
    panels = [PANEL_FNS[k](conn, as_of, weeks, rules) for k in R.PANELS if k in allowed]
    return {"as_o": str(as_of), "weeks": weeks, "panels": panels, "chain": chain(conn, as_of, allowed),
            "returns": returns(conn, allowed), "waiting": waiting(conn, user, as_of),
            "synced_at": _synced(conn)}


def wall(conn, user: dict, as_of: dt.date, weeks: int, saved: dict | None = None, *, tz: str = "UTC") -> dict:
    """The big screen: the same overview without what waits for people; in visitor mode (the default) without
    amounts of money or names of customers and suppliers."""
    out = build(conn, user, as_of, weeks, saved, tz=tz)
    out.pop("waiting")
    visitor = (saved or {}).get("visitor_mode", True)
    if visitor:
        out["panels"] = [R.redact(p) for p in out["panels"]]
        out["chain"] = [{**s, "count": None} if s.get("unit") == "currency" else s for s in out["chain"]]
    out["visitor_mode"] = visitor
    return out


def _synced(conn) -> str | None:
    """When the last ERPNext sync finished (the page refreshes when this changes)."""
    r = conn.execute("select max(finished_at) as t from erp_sync_runs").fetchone()
    return r["t"].isoformat() if r["t"] else None


SETTINGS = {"thresholds": {}, "visitor_mode": True}


def settings(conn) -> dict:
    rows = conn.execute("select distinct on (key) key, value from overview_settings order by key, id desc").fetchall()
    return {**SETTINGS, **{r["key"]: r["value"] for r in rows if r["key"] in SETTINGS}}


def set_setting(conn, email: str, key: str, value) -> dict:
    from psycopg.types.json import Jsonb  # noqa: PLC0415

    if key == "thresholds":
        value = {**settings(conn)["thresholds"], **R.check_thresholds(value)}
        value = {k: v for k, v in value.items()        # only what differs from the starting points is the company's
                 if (v["green"], v["amber"]) != tuple(R.THRESHOLDS[k][3:5])}
    elif key == "visitor_mode":
        if type(value) is not bool:
            raise ValueError("visitor mode is on or of")
    else:
        raise KeyError(key)
    conn.execute("insert into overview_settings (key, value, email) values (%s, %s, %s)", (key, Jsonb(value), email))
    return settings(conn)
