"""Ops hub object API (ADR-0007): ontology, search, object pages, relations, history, neighbourhood graph.

Each domain needs its view permission (ADR-0005); linked objects of domains a person may not see are left out.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException

from wqops.hub import permissions as P
from wqops.hub.ont import metrics as M
from wqops.hub.ont import schema as S

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
            label = spec["l"] if direction == "out" else spec["inv"]
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
            raise HTTPException(404, f"no object type {type_}")
        if not onto.can_see(u["roles"], type_):
            raise HTTPException(403, f"your role does not see {onto.types[type_]['label']} objects")
        return onto

    @app.get("/api/ont/schema")
    def ont_schema(u=Depends(user_dep)):
        return onto_fn().public(u["roles"])

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
            raise HTTPException(404, f"no {onto.types[type_]['label']} {key}")
        hist = c.execute("select kind, at, changes, event_id from ont_history where type = %s and key = %s "
                         "order by id desc limit 50", (type_, key)).fetchall()
        spec = onto.types[type_]
        return {**_brief(r), "label": spec["label"], "domain": spec["domain"], "source": spec["source"],
                "props": [{"name": p, "label": s["l"], "type": s["t"], "unit": s.get("u", ""),
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
        return {"nodes": nodes, "edges": [{"from": a, "link": ln, "label": onto.link(a[0], ln)["l"], "to": b}
                                          for a, ln, b in sorted(edges)], "truncated": len(seen) >= MAX_NODES}


def today(manifest: dict | None) -> dt.date:
    tz = ZoneInfo(manifest["company"]["timezone"]) if manifest else dt.UTC
    return dt.datetime.now(tz).date()


def mount_dashboard(app: FastAPI, conn_dep, user_dep, company) -> None:
    @app.get("/api/dashboard")
    def dashboard(days: int = 30, as_of: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        """The metrics this person may see (ADR-0007 items 3-4), with weekly trends."""
        if days not in (7, 30, 90):
            raise HTTPException(400, "days must be 7, 30 or 90")
        try:
            day = dt.date.fromisoformat(as_of) if as_of else today(company()[0])
        except ValueError as exc:
            raise HTTPException(400, "as_of must be a date like 2026-10-12") from exc
        names = [n for n in M.LABELS if P.allows(u["roles"], M.VIEW[n])]
        return {"as_of": str(day), "days": days, "metrics": [M.compute(c, n, day, days) for n in names],
                "trends": {n: M.weekly(c, n, day) for n in M.TRENDS if n in names}}

    @app.get("/api/dashboard/{name}")
    def metric(name: str, days: int = 30, as_of: str = "", u=Depends(user_dep), c=Depends(conn_dep)):
        if name not in M.LABELS:
            raise HTTPException(404, f"no metric {name}")
        if not P.allows(u["roles"], M.VIEW[name]):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[M.VIEW[name]]}")
        day = dt.date.fromisoformat(as_of) if as_of else today(company()[0])
        return M.compute(c, name, day, days) | {"as_of": str(day), "days": days}
