"""Measurement data (ADR-0020, 20c): files from measuring machines into incoming inspections, and control charts
of the hub's own readings. Plain code: no AI, no network.

An import is previewed first (nothing written), then signed with the importer's password. The print of the preview
must match what is signed, so a file or a mapping changed in between is refused. Readings that came from a file name
their import; the file is kept with it. Control charts and capability are computed by code from signed incoming
inspections (a subgroup per inspection) and recorded production measurements (one value per lot); too little data
is said so, never judged.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import statistics as stats

from psycopg.types.json import Jsonb

from wqops.hub.quality import cal_rules as CALR
from wqops.hub.quality import calibration as CAL
from wqops.hub.quality import iqc as I
from wqops.hub.quality import meas_rules as MR
from wqops.hub.quality import records as Q
from wqops.hub.quality import spc
from wqops.i18n import say


class MeasurementError(ValueError):
    pass


def _open(conn, ins_id: int, lock: bool = False) -> tuple[dict, list[dict]]:
    ins = conn.execute("select * from iqc_inspections where id = %s" + (" for update" if lock else ""),  # noqa: S608
                       (ins_id,)).fetchone()
    if ins is None:
        raise KeyError(ins_id)
    if ins["status"] != "in_progress":
        raise MeasurementError(say("{name} is {status}: readings can no longer be imported",
                                   name=ins['name'], status=ins['status'].replace('_', ' ')))
    return ins, I.plan(conn, ins["plan_id"])["characteristics"]


def _first_free(conn, ins: dict, chars: set[str]) -> int:
    """The first sample with none of these characteristics entered yet."""
    taken = {r["sample"] for r in conn.execute(
        "select sample from iqc_readings where inspection_id = %s and value is not null and characteristic = any(%s)",
        (ins["id"], list(chars)))}
    return next((s for s in range(1, ins["n"] + 1) if s not in taken), 1)


def preview(conn, ins_id: int, file_name: str, raw: bytes, *, mapping: dict | None = None,
            first_sample: int | None = None, gauge_id: int | None = None) -> dict:
    """What an import would do: the file's features matched to the plan, the samples its parts go to, the readings
    it would write (and those it would replace), and everything left out."""
    ins, chars = _open(conn, ins_id)
    try:
        parsed = MR.parse(file_name, raw)
        m = MR.match(parsed["features"], chars, mapping)
        start = first_sample if first_sample is not None else _first_free(conn, ins, set(m.values()) or {""})
        placed = MR.place(parsed, chars, ins["n"], start, m)
    except MR.MeasError as exc:
        raise MeasurementError(str(exc)) from exc
    sha = hashlib.sha256(raw).hexdigest()
    before = {(r["sample"], r["characteristic"]): float(r["value"]) for r in conn.execute(
        "select sample, characteristic, value from iqc_readings where inspection_id = %s and value is not null",
        (ins_id,))}
    replaces = [dict(r, before=before[(r["sample"], r["characteristic"])]) for r in placed["readings"]
                if (r["sample"], r["characteristic"]) in before and before[(r["sample"], r["characteristic"])]
                != r["value"]]
    done = conn.execute("select id, imported_by, imported_at from measurement_imports where inspection_id = %s and "
                        "sha256 = %s", (ins_id, sha)).fetchone()
    measured = sorted({r["characteristic"] for r in placed["readings"]})
    blocks = []
    other = [p for p in parsed.get("part_nos", []) if p.strip().lower() != ins["item_code"].strip().lower()]
    if other:
        blocks.append(f"the file is for part {', '.join(other)}, the inspection for {ins['item_code']}")
    gauge = None
    if gauge_id is not None:
        gauge = CAL.get(conn, gauge_id)
        named = {r["characteristic"]: r["gauge_code"] for r in conn.execute(
            "select characteristic, gauge_code from iqc_gauges where inspection_id = %s and gauge_id <> %s",
            (ins_id, gauge_id))}
        blocks += [f"{c} is measured with {named[c]} in this inspection; {gauge['code']} cannot be named for it too"
                   for c in measured if c in named]
    out = {"inspection": ins["name"], "file_name": file_name, "sha256": sha, "format": parsed["format"],
           "shape": parsed.get("shape"), "part_no": parsed.get("part_no"), "features": parsed["features"],
           "mapping": m, "first_sample": start, "n": ins["n"],
           "characteristics": [c["name"] for c in chars if c["kind"] == "measured"], **placed,
           "replaces": replaces, "measured": measured, "blocks": blocks,
           "gauge": {"id": gauge["id"], "code": gauge["code"]} if gauge else None,
           "already": {"id": done["id"], "by": done["imported_by"], "at": done["imported_at"].isoformat()}
           if done else None}
    out["print"] = _print(out)
    return out


def _print(p: dict) -> str:
    """Everything the signer saw that decides what is written: the file, the matching, the samples, the readings,
    the readings they replace and the equipment."""
    return hashlib.sha256(json.dumps([p["sha256"], p["mapping"], p["first_sample"], p["readings"], p["replaces"],
                                      p["gauge"]], sort_keys=True).encode()).hexdigest()


def import_file(conn, user: dict, ins_id: int, file_name: str, raw: bytes, password: str, *,  # noqa: PLR0917
                seen: str, mapping: dict | None = None, first_sample: int | None = None,
                gauge_id: int | None = None, today: dt.date) -> dict:
    """Write the previewed readings, signed. The equipment, if named, is noted for every characteristic the file
    measured and must be in calibration today."""
    Q.check_signer(conn, user, password)
    with conn.transaction():
        ins, _ = _open(conn, ins_id, lock=True)
        p = preview(conn, ins_id, file_name, raw, mapping=mapping, first_sample=first_sample, gauge_id=gauge_id)
        if p["print"] != seen:
            raise MeasurementError(say("the file, the matching or the readings changed since the preview: preview "
                                       "again"))
        if p["already"]:
            raise MeasurementError(say("this file was imported into {name} before, by {by}",
                                       name=ins['name'], by=p['already']['by']))
        if not p["readings"]:
            raise MeasurementError(say("no reading in the file goes to a measured characteristic of the plan"))
        if p["blocks"]:
            raise MeasurementError("; ".join(p["blocks"]))
        g = None
        if gauge_id is not None:
            g = CAL.get(conn, gauge_id)
            ok, why = CALR.usable(g, today)
            if not ok:
                raise MeasurementError(say("{code}: {why}; measure with equipment in calibration",
                                           code=g['code'], why=why))
        left = p["problems"] + p["notes"]
        row = conn.execute(
            "insert into measurement_imports (inspection_id, file_name, sha256, format, content, mapping, samples, "
            "readings, left_out, gauge_id, gauge_code, imported_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s) returning *",
            (ins_id, file_name[:200], p["sha256"], p["format"], raw, Jsonb(p["mapping"]),
             Jsonb(dict(zip(p["parts"], p["samples"], strict=True))), len(p["readings"]), Jsonb(left),
             g["id"] if g else None, g["code"] if g else None, user["email"])).fetchone()
        now = dt.datetime.now(dt.UTC)
        for r in p["readings"]:
            conn.execute("update iqc_readings set value = %s, passed = null, entered_by = %s, entered_at = %s, "
                         "import_id = %s, inbox_id = null where inspection_id = %s and sample = %s and "
                         "characteristic = %s",
                         (r["value"], user["email"], now, row["id"], ins_id, r["sample"], r["characteristic"]))
        if g:
            for ch in p["measured"]:                     # only what the file gave values for
                I.set_gauge(conn, user["email"], ins_id, ch, g["id"], today=today)
        Q._sign(conn, user, f"Measurements imported from {file_name[:120]} ({len(p['readings'])} readings)",
                "measurement_import", row["id"], ins["name"])
        I.log(conn, "inspection", ins_id, user["email"], "imported",
              f"{file_name[:120]}: {len(p['readings'])} readings, samples {min(p['samples'])}-{max(p['samples'])}")
    return imported(conn, row["id"])


def imported(conn, import_id: int) -> dict:
    r = conn.execute("select id, inspection_id, file_name, sha256, format, mapping, samples, readings, left_out, "
                     "gauge_code, imported_by, imported_at from measurement_imports where id = %s",
                     (import_id,)).fetchone()
    if r is None:
        raise KeyError(import_id)
    return dict(r, imported_at=r["imported_at"].isoformat())


def imports(conn, ins_id: int) -> list[dict]:
    return [imported(conn, r["id"]) for r in conn.execute(
        "select id from measurement_imports where inspection_id = %s order by id", (ins_id,))]


def content(conn, import_id: int) -> tuple[str, bytes]:
    r = conn.execute("select file_name, content from measurement_imports where id = %s", (import_id,)).fetchone()
    if r is None:
        raise KeyError(import_id)
    return r["file_name"], bytes(r["content"])


# ---------------------------------------------------------------- control charts of the hub's readings

SIGNED = ("judged", "released", "rejected")


def parameters(conn) -> list[dict]:
    """Item and characteristic pairs with measured values: from signed incoming inspections and recorded production
    measurements."""
    out = [dict(r, source="incoming") for r in conn.execute(
        "select i.item_code, r.characteristic as parameter, count(distinct i.id) as inspections from iqc_readings r "
        "join iqc_inspections i on i.id = r.inspection_id where r.value is not null and i.status = any(%s) "
        "group by 1, 2 order by 1, 2", (list(SIGNED),))]
    out += [dict(r, source="production") for r in conn.execute(
        "select p.item_code, s.name as parameter, count(*) as inspections from prod_steps s join prod_records p on "
        "p.id = s.record_id where s.kind = 'measure' and s.value is not null and s.verdict is not null and "
        "p.status <> 'cancelled' group by 1, 2 order by 1, 2")]
    return out


def subgroups(conn, source: str, item_code: str, parameter: str, limit: int = 100) -> list[dict]:
    """The measured values of one item and characteristic in time order, a subgroup per signed incoming inspection or
    per production record, each with the limits it was judged against (also used by the histogram, 22a)."""
    if source == "incoming":
        rows = conn.execute(
            "select i.id, i.name, coalesce(i.signed_at, i.created_at) as at, i.plan_id, "
            "array_agg(r.value order by r.sample) as vals from iqc_inspections i join iqc_readings r on "
            "r.inspection_id = i.id where i.item_code = %s and r.characteristic = %s and r.value is not null and "
            "i.status = any(%s) group by i.id order by 3, 1", (item_code, parameter, list(SIGNED))).fetchall()[-limit:]
        groups = []
        for r in rows:
            c = next((x for x in I.plan(conn, r["plan_id"])["characteristics"] if x["name"] == parameter), {})
            groups.append({"inspection": r["name"], "date": r["at"].date().isoformat(),
                           "values": [float(v) for v in r["vals"]], "min": c.get("lsl"), "max": c.get("usl")})
    elif source == "production":
        rows = conn.execute(
            "select p.name, s.done_at, s.value, s.low, s.high from prod_steps s join prod_records p on p.id = "
            "s.record_id where p.item_code = %s and s.name = %s and s.kind = 'measure' and s.value is not null and "
            "s.verdict is not null and p.status <> 'cancelled' order by s.done_at, s.id",
            (item_code, parameter)).fetchall()[-limit:]
        groups = [{"inspection": r["name"], "date": r["done_at"].date().isoformat(), "values": [float(r["value"])],
                   "min": float(r["low"]) if r["low"] is not None else None,
                   "max": float(r["high"]) if r["high"] is not None else None} for r in rows]
    else:
        raise MeasurementError(say("the source is incoming or production"))
    for g in groups:
        g["min"] = float(g["min"]) if g["min"] is not None else None
        g["max"] = float(g["max"]) if g["max"] is not None else None
    return groups


def spc_for(conn, source: str, item_code: str, parameter: str, limit: int = 100) -> dict:
    """The control chart, its signals and capability; the limits are the latest plan's or template's."""
    groups = subgroups(conn, source, item_code, parameter, limit)
    out = {"source": source, "item_code": item_code, "parameter": parameter,
           "inspections": [g["inspection"] for g in groups]}
    if not groups:
        return out | {"enough_data": False, "note": "No measured values for this item and characteristic.",
                      "subgroups": 0}
    res = out | spc.chart(groups)
    values = [v for g in groups for v in g["values"]]
    if res.get("enough_data") and res.get("capability") is None:
        res["capability_note"] = ("unknown: the plan has no lower and upper limit for it" if groups[-1]["min"] is None
                                  or groups[-1]["max"] is None else "unknown: too few values, or no spread")
    cap = res.get("capability")
    if res.get("enough_data") and cap and cap["n"] < 25:
        res["capability_note"] = f"only {cap['n']} values: capability this early is a rough guide"
    if res.get("limits_note") and cap:
        res["capability_note"] = "; ".join(x for x in (res.get("capability_note"), res["limits_note"]) if x)
    res["values"] = len(values)
    res["mean"] = stats.fmean(values)
    return res
