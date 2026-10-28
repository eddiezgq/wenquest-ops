"""Ops hub object API (ADR-0007): ontology, search, object pages, relations, history, neighbourhood graph.

Each domain needs its view permission (ADR-0005); linked objects of domains a person may not see are left out.
"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops import i18n as I18N
from wqops.hub import permissions as P
from wqops.hub.ont import metrics as M
from wqops.hub.ont import overview as OV
from wqops.hub.ont import schema as S
from wqops.i18n import say

MAX_NODES = 150
MAX_LIST = 200


def _brief(r: dict) -> dict:
    return {"type": r["type"], "key": r["key"], "title": r["title"], "deleted": r.get("deleted", False)}


def objects_by_keys(conn, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    if not pairs:
        return {}
    rows = conn.execute("select type, key, title, deleted from ont_objects where (type, key) in "
                        "(select * from unnest(%s::text[], %s::text[]))",
                        ([p[0] for p in pairs], [p[1] for p in pairs])).fetchall()
    return {(r["type"], r["key"]): r for r in rows}


def relations(conn, onto: S.Ontology, roles, type_: str, key: str) -> list[dict]:
    """Outgoing and incoming links of one object, grouped by link, with the far object's title."""
    out = conn.execute("select type as link, dst_type as t, dst_key as k from ont_links where src_type = %s and "
                       "src_key = %s order by type, dst_key", (type_, key)).fetchall()
    inc = conn.execute("select type as link, src_type as t, src_key as k from ont_links where dst_type = %s and "
                       "dst_key = %s order by src_type, type, src_key", (type_, key)).fetchall()
    found = objects_by_keys(conn, [(r["t"], r["k"]) for r in out + inc])
    groups: dict[tuple[str, str, str], dict] = {}
    for direction, rows in (("out", out), ("in", inc)):
        for r in rows:
            if not onto.can_see(roles, r["t"]):
                continue
            spec = onto.link(type_, r["link"]) if direction == "out" else onto.link(r["t"], r["link"])
            label = I18N.label(spec["l"] if direction == "out" else spec["inv"])
            g = groups.setdefault((direction, r["link"], r["t"]), {"direction": direction, "link": r["link"],
                                                                    "label": label, "type": r["t"], "objects": []})
            o = found.get((r["t"], r["k"]))
            g["objects"].append({"type": r["t"], "key": r["k"], "title": o["title"] if o else r["k"],
                                 "known": o is not None and not o["deleted"]})
    return list(groups.values())


def mount(app: FastAPI, conn_dep, user_dep, onto_fn=S.get) -> None:
    def visible(u: dict, type_: str) -> S.Ontology:
        onto = onto_fn()
        if type_ not in onto.types:
            raise HTTPException(404, say("no object type {type}", type=type_))
        if not onto.can_see(u["roles"], type_):
            raise HTTPException(403, say("your role does not see {label} objects",
                                         label=I18N.label(onto.types[type_]["label"])))
        return onto

    @app.get("/api/ont/schema")
    def ont_schema(u=Depends(user_dep)):
        return I18N.localize(onto_fn().public(u["roles"]), S.LABEL_KEYS)

    @app.get("/api/ont/search")
    def ont_search(q: str = "", type: str = "", limit: int = 20, u=Depends(user_dep), c=Depends(conn_dep)):
        onto = onto_fn()
        types = [t for t in ([type] if type else onto.types) if onto.can_see(u["roles"], t)]
        words = [w for w in q.lower().split() if w]
        sql = "select type, key, title, deleted from ont_objects where not deleted and type = any(%s)"
        args: list = [types]
        for w in words:
            sql += " and search like %s"
            args.append(f"%{w.replace('%', '').replace('_', '')}%")
        sql += " order by (lower(key) = %s) desc, type, key limit %s"
        args += [q.lower(), max(1, min(limit, MAX_LIST))]
        return [_brief(r) for r in c.execute(sql, args).fetchall()]

    @app.get("/api/ont/objects/{type_}")
    def ont_list(type_: str, offset: int = 0, limit: int = 50, u=Depends(user_dep), c=Depends(conn_dep)):
        visible(u, type_)
        total = c.execute("select count(*) as n from ont_objects where type = %s and not deleted", (type_,)).fetchone()
        rows = c.execute("select type, key, title, props, deleted from ont_objects where type = %s and not deleted "
                         "order by key offset %s limit %s", (type_, max(0, offset), max(1, min(limit, MAX_LIST))))
        return {"total": total["n"], "objects": [_brief(r) | {"props": r["props"]} for r in rows.fetchall()]}

    @app.get("/api/ont/objects/{type_}/{key:path}")
    def ont_object(type_: str, key: str, u=Depends(user_dep), c=Depends(conn_dep)):
        onto = visible(u, type_)
        r = c.execute("select * from ont_objects where type = %s and key = %s", (type_, key)).fetchone()
        if r is None:
            raise HTTPException(404, say("no {label} {key}", label=I18N.label(onto.types[type_]["label"]), key=key))
        hist = c.execute("select kind, at, changes, event_id from ont_history where type = %s and key = %s "
                         "order by id desc limit 50", (type_, key)).fetchall()
        spec = onto.types[type_]
        from wqops.hub.ont import anomaly as AN  # noqa: PLC0415

        rules = AN.load_rules()
        about = c.execute("select * from anomalies where status in ('open', 'ack', 'doing') and rule = any(%s) and "
                          "((subject_type = %s and subject_key = %s) or related @> %s::jsonb) order by id",
                          (AN.visible_rules(u["roles"], rules), type_, key, json.dumps([[type_, key]]))).fetchall()
        return {**_brief(r), "label": I18N.label(spec["label"]), "domain": spec["domain"],
                "source": I18N.label(spec["source"]),
                "anomalies": [AN.public(a, rules) for a in about],
                "props": [{"name": p, "label": I18N.label(s["l"]), "type": s["t"], "unit": s.get("u", ""),
                           "value": r["props"][p]} for p, s in spec["props"].items() if p in r["props"]],
                "relations": relations(c, onto, u["roles"], type_, key), "history": hist}

    @app.get("/api/ont/graph/{type_}/{key:path}")
    def ont_graph(type_: str, key: str, depth: int = 1, u=Depends(user_dep), c=Depends(conn_dep)):
        onto = visible(u, type_)
        seen = {(type_, key)}
        frontier = [(type_, key)]
        edges = set()
        for _ in range(max(1, min(depth, 3))):
            nxt = []
            for t, k in frontier:
                rows = c.execute("select type, src_type, src_key, dst_type, dst_key from ont_links where "
                                 "(src_type = %s and src_key = %s) or (dst_type = %s and dst_key = %s)",
                                 (t, k, t, k)).fetchall()
                for r in rows:
                    a, b = (r["src_type"], r["src_key"]), (r["dst_type"], r["dst_key"])
                    if not (onto.can_see(u["roles"], a[0]) and onto.can_see(u["roles"], b[0])):
                        continue
                    for n in (a, b):
                        if n not in seen and len(seen) < MAX_NODES:
                            seen.add(n)
                            nxt.append(n)
                    if a in seen and b in seen:
                        edges.add((a, r["type"], b))
            frontier = nxt
        found = objects_by_keys(c, list(seen))
        nodes = [{"type": t, "key": k, "title": found[(t, k)]["title"] if (t, k) in found else k,
                  "known": (t, k) in found} for t, k in sorted(seen)]
        return {"nodes": nodes, "edges": [{"from": a, "link": ln, "label": I18N.label(onto.link(a[0], ln)["l"]),
                                           "to": b}
                                          for a, ln, b in sorted(edges)], "truncated": len(seen) >= MAX_NODES}


def today(manifest: dict | None) -> dt.date:
    tz = ZoneInfo(manifest["company"]["timezone"]) if manifest else dt.UTC
    return dt.datetime.now(tz).date()


def mount_dashboard(app: FastAPI, conn_dep, user_dep, company) -> None:
    @app.get("/api/dashboard")
    def dashboard(days: int = 30, as_of: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        """The metrics this person may see (ADR-0007 items 3-4), with weekly trends."""
        if days not in (7, 30, 90):
            raise HTTPException(400, say("days must be 7, 30 or 90"))
        try:
            day = dt.date.fromisoformat(as_of) if as_of else today(company()[0])
        except ValueError as exc:
            raise HTTPException(400, say("as_of must be a date like 2026-10-12")) from exc
        names = [n for n in M.LABELS if P.allows(u["roles"], M.VIEW[n])]
        return {"as_of": str(day), "days": days, "metrics": [M.compute(c, n, day, days) for n in names],
                "trends": {n: M.weekly(c, n, day) for n in M.TRENDS if n in names}}

    def _day(as_of: str) -> dt.date:
        try:
            return dt.date.fromisoformat(as_of) if as_of else today(company()[0])
        except ValueError as exc:
            raise HTTPException(400, say("as_of must be a date like 2026-10-12")) from exc

    def _tz() -> str:
        return ((company()[0] or {}).get("company") or {}).get("timezone") or "UTC"

    def _weeks(weeks: int) -> int:
        if weeks not in (8, 13, 26):
            raise HTTPException(400, say("weeks must be 8, 13 or 26"))
        return weeks

    @app.get("/api/overview")
    def overview(weeks: int = 8, as_of: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        """The company overview (ADR-0018): the panels, the chain and what waits, as this person may see them."""
        if not P.allows(u["roles"], "dashboard:view"):
            raise HTTPException(403, say("your role does not allow: {dashboard_view}",
                                         dashboard_view=P.describe('dashboard:view')))
        st = OV.settings(c)
        return OV.build(c, u, _day(as_of), _weeks(weeks), st, tz=_tz()) | {
            "visitor_mode": st["visitor_mode"],
            "thresholds": I18N.localize(OV.R.thresholds(st["thresholds"]), {"what"}),
            "threshold_note": I18N.label(OV.R.NOTE), "can_configure": P.allows(u["roles"], "settings:edit")}

    @app.get("/api/overview/wall")
    def overview_wall(weeks: int = 8, u=Depends(user_dep), c=Depends(conn_dep)):
        """The big screen; in visitor mode without amounts of money or names."""
        if not P.allows(u["roles"], "dashboard:view"):
            raise HTTPException(403, say("your role does not allow: {dashboard_view}",
                                         dashboard_view=P.describe('dashboard:view')))
        return OV.wall(c, u, _day(""), _weeks(weeks), OV.settings(c), tz=_tz()) | {
            "company": (company()[0] or {}).get("company", {}).get("name")}

    @app.post("/api/overview/settings")
    async def overview_settings(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        if not P.allows(u["roles"], "settings:edit"):
            raise HTTPException(403, say("your role does not allow: {settings_edit}",
                                         settings_edit=P.describe('settings:edit')))
        try:
            d = await request.json()
        except ValueError as exc:
            raise HTTPException(400, say("the request is not JSON")) from exc
        if not isinstance(d, dict):
            raise HTTPException(400, say("send a key and a value"))
        try:
            return OV.set_setting(c, u["email"], str(d.get("key") or ""), d.get("value"))
        except KeyError as exc:
            raise HTTPException(404, say("no such setting")) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/dashboard/{name}")
    def metric(name: str, days: int = 30, as_of: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        if name not in M.LABELS:
            raise HTTPException(404, say("no metric {name}", name=name))
        if not P.allows(u["roles"], M.VIEW[name]):
            raise HTTPException(403, say("your role does not allow: {PERMISSIONS}",
                                         PERMISSIONS=P.describe(M.VIEW[name])))
        day = dt.date.fromisoformat(as_of) if as_of else today(company()[0])
        return M.compute(c, name, day, days) | {"as_of": str(day), "days": days}


def visible_chain(onto: S.Ontology, roles, out: dict) -> dict:
    """Keep the steps a person may see, and only those still connected to the root."""
    for part in ("causes", "impact"):
        reach = {tuple(out["root"])}
        kept = []
        for s in sorted(out[part], key=lambda s: s["depth"]):
            frm = tuple(s["from"])
            to = tuple(s["to"]) if s["to"] else None
            if frm in reach and (to is None or onto.can_see(roles, to[0])):
                kept.append(s)
                if to:
                    reach.add(to)
        out[part] = kept
    used = {tuple(out["root"])} | {tuple(s[e]) for p in ("causes", "impact") for s in out[p] for e in ("from", "to")
                                    if s[e]}
    out["nodes"] = [n for n in out["nodes"] if (n["type"], n["key"]) in used]
    return out


def mount_anomalies(app: FastAPI, conn_dep, user_dep, company, onto_fn=S.get) -> None:
    from wqops.hub.ont import anomaly as AN  # noqa: PLC0415
    from wqops.hub.ont import chain as CH  # noqa: PLC0415

    def day() -> dt.date:
        return today(company()[0])

    def check(u: dict, row: dict, rules: dict) -> None:
        if row["rule"] not in AN.visible_rules(u["roles"], rules):
            raise HTTPException(403, say("your role does not see this anomaly"))

    @app.get("/api/anomalies/rules")
    def anomaly_rules(u=Depends(user_dep)):
        rules = AN.load_rules()
        return [I18N.localize({"id": rid, **r}, {"name", "hint"}) for rid, r in rules.items()
                if rid in AN.visible_rules(u["roles"], rules)]

    @app.get("/api/anomalies")
    def anomalies(status: str = "active", u=Depends(user_dep), c=Depends(conn_dep)):
        rules = AN.load_rules()
        sql, args = "select * from anomalies where rule = any(%s)", [AN.visible_rules(u["roles"], rules)]
        if status == "active":
            sql += " and status in ('open', 'ack', 'doing')"
        elif status != "all":
            sql += " and status = %s"
            args.append(status)
        sql += " order by case severity when 'critical' then 0 when 'warn' then 1 else 2 end, id desc limit 500"
        return [AN.public(r, rules) for r in c.execute(sql, args).fetchall()]

    @app.get("/api/anomalies/{aid}")
    def anomaly(aid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        rules = AN.load_rules()
        row = c.execute("select * from anomalies where id = %s", (aid,)).fetchone()
        if row is None:
            raise HTTPException(404, say("no such anomaly"))
        check(u, row, rules)
        log = c.execute("select at, email, action, note from anomaly_log where anomaly_id = %s order by id",
                        (aid,)).fetchall()
        chain = CH.explain(c, row["subject_type"], row["subject_key"], day())
        return AN.public(row, rules) | {"log": [dict(x, at=x["at"].isoformat()) for x in log],
                                        "explain": visible_chain(onto_fn(), u["roles"], chain)}

    @app.post("/api/anomalies/{aid}/status")
    async def anomaly_status(aid: int, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        data = await request.json()
        rules = AN.load_rules()
        row = c.execute("select * from anomalies where id = %s", (aid,)).fetchone()
        if row is None:
            raise HTTPException(404, say("no such anomaly"))
        check(u, row, rules)
        try:
            row = AN.set_status(c, aid, str(data.get("status", "")), u["email"], str(data.get("note", "")))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return AN.public(row, rules)

    @app.get("/api/explain/{type_}/{key:path}")
    def explain(type_: str, key: str, u=Depends(user_dep), c=Depends(conn_dep)):
        onto = onto_fn()
        if not onto.can_see(u["roles"], type_):
            raise HTTPException(403 if type_ in onto.types else 404, say("cannot explain {type}", type=type_))
        return visible_chain(onto, u["roles"], CH.explain(c, type_, key, day()))
