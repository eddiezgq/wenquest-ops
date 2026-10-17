"""Quality tools, step 22a (ADR-0022): Pareto charts, histograms, scatter plots and check sheets, computed from the
records the hub already keeps. Nothing is entered twice: a chart reads signed incoming inspections, nonconformance
reports, complaints, production measurements and check sheets, and every bar or point names the records behind it.
A record with no value for the chosen category is counted as "not recorded", never left out. No AI, no network.
"""

from __future__ import annotations

import datetime as dt
import re

from psycopg.types.json import Jsonb

from wqops.hub.quality import iqc as I
from wqops.hub.quality import measurements as ME
from wqops.hub.quality import records as Q
from wqops.hub.quality import sampling as S
from wqops.hub.quality import tools_rules as TR
from wqops.hub.quality import workflow as W

REFS = 50                                        # records listed per bar; the count is always complete
SOURCES = {
    "ncr": {"label": "Nonconformance reports", "measure": "reports",
            "by": {"item_code": "Item", "supplier": "Supplier", "severity": "Severity", "disposition": "Disposition"}},
    "incoming": {"label": "Incoming inspection failures", "measure": "failed readings",
                 "by": {"characteristic": "Characteristic", "supplier": "Supplier", "item_code": "Item"}},
    "complaints": {"label": "Complaints", "measure": "complaints",
                   "by": {"item_code": "Item", "customer": "Customer", "source": "Source"}},
    "check_sheet": {"label": "Check sheets", "measure": "counted", "by": {"category": "Category", "place": "Place",
                                                                         "item_code": "Item"}},
}


class ToolsError(ValueError):
    pass


def _custom_choices(conn) -> dict[str, str]:
    """The company's own choice fields on nonconformance reports (ADR-0015), such as a defect type."""
    fields = W.of(conn, "ncr").get("fields") or {}
    return {f"custom:{k}": f["label"] for k, f in fields.items()
            if f.get("type") == "choice"}


def options(conn) -> dict:
    """What a Pareto chart can count, by what, and the check sheet forms."""
    out = {k: {"label": v["label"], "measure": v["measure"], "by": dict(v["by"])} for k, v in SOURCES.items()}
    out["ncr"]["by"].update(_custom_choices(conn))
    return {"sources": out, "forms": forms(conn)}


def _day(v, what: str) -> dt.date | None:
    if v in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError as exc:
        raise ToolsError(f"{what}: a date like 2026-10-31") from exc


def _key(v) -> str:
    v = "" if v is None else str(v).strip()
    return v or TR.NOT_RECORDED


def pareto_for(conn, source: str, by: str, *, since=None, until=None,  # noqa: PLR0912, PLR0915
               form_id: int | None = None) -> dict:
    if source not in SOURCES:
        raise ToolsError(f"count one of: {', '.join(SOURCES)}")
    dims = dict(SOURCES[source]["by"]) | (_custom_choices(conn) if source == "ncr" else {})
    if by not in dims:
        raise ToolsError(f"group {SOURCES[source]['label'].lower()} by one of: {', '.join(dims.values())}")
    d0, d1 = _day(since, "from"), _day(until, "to")
    if d0 and d1 and d1 < d0:
        raise ToolsError("the period ends before it starts")
    lo = d0 or dt.date(1900, 1, 1)
    hi = (d1 or dt.date(9999, 12, 30)) + dt.timedelta(days=1)
    counts: dict[str, float] = {}
    refs: dict[str, list[dict]] = {}
    records = 0

    def add(key: str, n: float, ref: dict) -> None:
        counts[key] = counts.get(key, 0) + n
        lst = refs.setdefault(key, [])
        if len(lst) < REFS and (not lst or lst[-1]["id"] != ref["id"]):
            lst.append(ref)

    if source == "ncr":
        for r in conn.execute("select id, name, title, item_code, supplier, severity, disposition, custom from "
                              "ncr_records where status <> 'cancelled' and created_at >= %s and created_at < %s "
                              "order by id", (lo, hi)):
            records += 1
            v = (r["custom"] or {}).get(by[7:]) if by.startswith("custom:") else r[by]
            add(_key(v), 1, {"kind": "ncr", "id": r["id"], "name": r["name"], "title": r["title"]})
    elif source == "incoming":
        plans: dict[int, dict] = {}
        for ins in conn.execute("select id, name, plan_id, item_code, supplier from iqc_inspections where status = "
                                "any(%s) and signed_at >= %s and signed_at < %s order by id",
                                (list(ME.SIGNED), lo, hi)):
            records += 1
            if ins["plan_id"] not in plans:
                plans[ins["plan_id"]] = {c["name"]: c for c in I.plan(conn, ins["plan_id"])["characteristics"]}
            chars = plans[ins["plan_id"]]
            for rd in I.readings(conn, ins["id"]):
                c = chars.get(rd["characteristic"])
                if c is None or S.conforms(c, float(rd["value"]) if rd["value"] is not None else None,
                                           rd["passed"]) is not False:
                    continue
                v = rd["characteristic"] if by == "characteristic" else ins[by]
                add(_key(v), 1, {"kind": "iqc", "id": ins["id"], "name": ins["name"], "title": rd["characteristic"]})
    elif source == "complaints":
        for r in conn.execute("select id, name, item_code, customer, source, description from complaints where status "
                              "<> 'cancelled' and received_on >= %s and received_on < %s order by id", (lo, hi)):
            records += 1
            add(_key(r[by]), 1, {"kind": "complaint", "id": r["id"], "name": r["name"],
                                 "title": r["description"][:80]})
    else:
        if not form_id:
            raise ToolsError("choose the check sheet form")
        form(conn, form_id)
        for r in conn.execute("select * from check_sheets where form_id = %s and on_date >= %s and on_date < %s "
                              "order by id", (form_id, lo, hi)):
            records += 1
            ref = {"kind": "check_sheet", "id": r["id"], "name": r["name"], "title": f"{r['on_date']} {r['place']}"}
            for cat, n in (r["counts"] or {}).items():
                if n:
                    add(_key(cat if by == "category" else r[by]), int(n), ref)
    bars = TR.pareto(counts)
    for b in bars:
        b["records"] = refs.get(b["key"], [])
    total = sum(counts.values())
    out = {"source": source, "by": by, "by_label": dims[by], "measure": SOURCES[source]["measure"],
           "since": d0.isoformat() if d0 else None, "until": d1.isoformat() if d1 else None, "records": records,
           "total": total, "bars": bars, "vital_few": TR.vital_few(bars) if bars else 0}
    nr = counts.get(TR.NOT_RECORDED, 0)
    if nr:
        out["note"] = (f"{int(nr)} of {int(total)} {SOURCES[source]['measure']} have no {dims[by].lower()} recorded; "
                       "they are shown as their own bar")
    if not bars:
        out["note"] = "Nothing to count in this period."
    return out


def histogram_for(conn, source: str, item_code: str, parameter: str) -> dict:
    """The distribution of the measured values beside their capability (the same values as the control chart)."""
    groups = ME.subgroups(conn, source, item_code, parameter, limit=1000)
    values = [v for g in groups for v in g["values"]]
    out = {"source": source, "item_code": item_code, "parameter": parameter, "values": len(values)}
    if len(values) < 2:
        return out | {"enough_data": False, "note": "At least 2 measured values are needed for a histogram."}
    lo, hi = groups[-1]["min"], groups[-1]["max"]
    out |= {"enough_data": True, "histogram": TR.histogram(values, lo, hi)}
    spc = ME.spc_for(conn, source, item_code, parameter, limit=1000)
    out["capability"] = spc.get("capability")
    out["capability_note"] = spc.get("capability_note") or (None if spc.get("capability") else
                                                            "unknown: needs both limits and enough data")
    if any((g["min"], g["max"]) != (lo, hi) for g in groups):
        out["limits_note"] = "the limits changed over time: the lines show the latest limits"
    return out


def scatter_for(conn, source: str, item_code: str, x: str, y: str, *, limit: int = 2000) -> dict:
    """Two characteristics of the same item measured on the same piece: a sample of an incoming inspection, or one
    production record."""
    if x == y:
        raise ToolsError("choose two different characteristics")
    if source == "incoming":
        rows = conn.execute(
            "select i.id, i.name, a.sample, a.value as x, b.value as y from iqc_inspections i "
            "join iqc_readings a on a.inspection_id = i.id and a.characteristic = %s "
            "join iqc_readings b on b.inspection_id = i.id and b.characteristic = %s and b.sample = a.sample "
            "where i.item_code = %s and i.status = any(%s) and a.value is not null and b.value is not null "
            "order by i.signed_at, i.id, a.sample limit %s", (x, y, item_code, list(ME.SIGNED), limit)).fetchall()
        pts = [{"x": float(r["x"]), "y": float(r["y"]), "label": f"{r['name']} sample {r['sample']}",
                "ref": {"kind": "iqc", "id": r["id"], "name": r["name"]}} for r in rows]
    elif source == "production":
        rows = conn.execute(
            "select p.id, p.name, a.value as x, b.value as y from prod_records p "
            "join prod_steps a on a.record_id = p.id and a.name = %s and a.kind = 'measure' "
            "join prod_steps b on b.record_id = p.id and b.name = %s and b.kind = 'measure' "
            "where p.item_code = %s and p.status <> 'cancelled' and a.value is not null and b.value is not null "
            "and a.verdict is not null and b.verdict is not null order by a.done_at, p.id limit %s",
            (x, y, item_code, limit)).fetchall()
        pts = [{"x": float(r["x"]), "y": float(r["y"]), "label": r["name"],
                "ref": {"kind": "prod_record", "id": r["id"], "name": r["name"]}} for r in rows]
    else:
        raise ToolsError("the source is incoming or production")
    return {"source": source, "item_code": item_code, "x": x, "y": y, "points": pts,
            "fit": TR.correlation([(p["x"], p["y"]) for p in pts])}


# ---------------------------------------------------------------- check sheets

def _log(conn, form_id: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into check_sheet_log (form_id, email, action, note) values (%s, %s, %s, %s)",
                 (form_id, email, action, note[:2000]))


def forms(conn, active_only: bool = False) -> list[dict]:
    q = ("select * from check_sheet_forms where active order by name" if active_only
         else "select * from check_sheet_forms order by active desc, name")
    return conn.execute(q).fetchall()


def form(conn, form_id: int) -> dict:
    row = conn.execute("select * from check_sheet_forms where id = %s", (form_id,)).fetchone()
    if row is None:
        raise KeyError(form_id)
    return row


def new_form(conn, email: str, name: str, categories) -> dict:
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:200]
    if not name:
        raise ToolsError("give the form a name")
    if not isinstance(categories, list):
        raise ToolsError("list the categories to count")
    cats, seen = [], set()
    for raw in categories:
        c = re.sub(r"\s+", " ", str(raw or "")).strip()[:120]
        if c and c.lower() not in seen:
            seen.add(c.lower())
            cats.append(c)
    if not cats:
        raise ToolsError("list at least one category to count")
    if len(cats) > 40:
        raise ToolsError("a check sheet has at most 40 categories")
    if any(c.lower() == TR.NOT_RECORDED for c in cats):
        raise ToolsError(f"“{TR.NOT_RECORDED}” is kept for missing values; name the category")
    if conn.execute("select 1 from check_sheet_forms where lower(name) = lower(%s)", (name,)).fetchone():
        raise ToolsError(f"there is already a form called {name}")
    with conn.transaction():
        row = conn.execute("insert into check_sheet_forms (name, categories, created_by) values (%s, %s, %s) "
                           "returning *", (name, cats, email)).fetchone()
        _log(conn, row["id"], email, "created", f"{name}: {', '.join(cats)}")
    return row


def retire_form(conn, email: str, form_id: int, active: bool = False) -> dict:
    form(conn, form_id)
    with conn.transaction():
        row = conn.execute("update check_sheet_forms set active = %s where id = %s returning *",
                           (active, form_id)).fetchone()
        _log(conn, form_id, email, "back in use" if active else "retired")
    return row


def sheets(conn, form_id: int | None = None, limit: int = 200) -> list[dict]:
    return conn.execute("select s.*, f.name as form from check_sheets s join check_sheet_forms f on f.id = s.form_id "
                        "where %s::bigint is null or s.form_id = %s order by s.on_date desc, s.id desc limit %s",
                        (form_id, form_id, limit)).fetchall()


def record(conn, user: dict, form_id: int, data: dict, password: str, *, today: dt.date) -> dict:
    """A tally on a form, signed with the counter's password. Every category of the form gets a whole count (0 when
    nothing was seen); categories the form does not have are refused."""
    f = form(conn, form_id)
    if not f["active"]:
        raise ToolsError(f"{f['name']} is retired: use the form now in use")
    raw = data.get("counts")
    if not isinstance(raw, dict):
        raise ToolsError("give a count for each category")
    extra = [k for k in raw if k not in f["categories"]]
    if extra:
        raise ToolsError(f"{f['name']} does not count {', '.join(map(str, extra[:5]))}")
    counts = {}
    for c in f["categories"]:
        v = raw.get(c, 0)
        if isinstance(v, bool) or not isinstance(v, (int, str)) or not str(v).strip().isdigit():
            raise ToolsError(f"{c}: a whole number, 0 or more")
        counts[c] = int(str(v).strip())
        if counts[c] > 1_000_000:
            raise ToolsError(f"{c}: at most 1,000,000")
    on = _day(data.get("on_date"), "the day counted") or today
    if on > today:
        raise ToolsError("the day counted cannot be in the future")
    item = str(data.get("item_code") or "").strip()[:140] or None
    place = re.sub(r"\s+", " ", str(data.get("place") or "")).strip()[:200]
    Q.check_signer(conn, user, password)
    with conn.transaction():
        name = Q._next_name(conn, "check_sheets", "CS")
        row = conn.execute(
            "insert into check_sheets (name, form_id, on_date, item_code, place, counts, total, note, signed_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
            (name, form_id, on, item, place, Jsonb(counts), sum(counts.values()),
             str(data.get("note") or "").strip()[:2000], user["email"])).fetchone()
        Q._sign(conn, user, f"Check sheet recorded ({sum(counts.values())} counted)", "check_sheet", row["id"], name)
    return row | {"form": f["name"]}
