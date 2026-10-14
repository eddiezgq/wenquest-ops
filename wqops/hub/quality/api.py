"""Quality endpoints (ADR-0009, ADR-0010): nonconformance reports, 8D, corrective and preventive actions, incoming
inspection, supplier facts, SPC, signatures.

Reading needs quality:view; every change needs quality:edit, except that an action's owner may mark it done.
Signed steps take the signer's password in the request body.
After a change the ops hub objects are brought up to date, so pages and anomalies see it at once.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Request

from wqops.hub import drafts as D
from wqops.hub import permissions as P
from wqops.hub.ont import api as OA
from wqops.hub.ont import project as OP
from wqops.hub.quality import incoming as IN
from wqops.hub.quality import records as Q
from wqops.hub.quality import workflow as W


def _iso(row: dict) -> dict:
    """Dates as ISO text and numerics as numbers, for JSON."""
    return {k: v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else float(v) if isinstance(v, Decimal) else v
            for k, v in row.items()}


def mount(app: FastAPI, conn_dep, user_dep, company) -> None:  # noqa: PLR0915 - one route per step
    def need(u: dict, perm: str) -> None:
        if not P.allows(u["roles"], perm):
            raise HTTPException(403, f"your role does not allow: {P.PERMISSIONS[perm]}")

    def run(c, fn):
        try:
            out = fn()
        except Q.QualityError as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, "not found") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        OP.project(c, manifest=company()[0])
        return out

    async def body(request: Request) -> dict:
        raw = await request.body()
        return (await request.json()) if raw else {}

    def ncr_view(c, row: dict) -> dict:
        e = c.execute("select * from eightd where ncr_id = %s", (row["id"],)).fetchone()
        capas = c.execute("select c.id, c.name, c.title, c.status, c.kind from capa_ncrs l join capas c on "
                          "c.id = l.capa_id where l.ncr_id = %s order by c.id", (row["id"],)).fetchall()
        types = Q.disposition_types(c, active_only=False)
        return _iso(row) | {"history": Q.history(c, "ncr", row["id"]), "signatures": Q.signatures(c, "ncr", row["id"]),
                            "capas": capas, "eightd": _iso(e) if e else None, "sections": Q.SECTIONS,
                            "dispositions": {k: {"name": t["name"], "requires_approval": t["requires_approval"],
                                                 "active": t["active"]} for k, t in types.items()},
                            "workflow": wf_brief(c, "ncr", row)}

    def wf_brief(c, kind: str, row: dict) -> dict:
        """The workflow version the record runs under and what can happen next (ADR-0015)."""
        v = W.version(c, kind, row.get("workflow_version"))
        nxt = [{"step": k, "label": s.get("label", k), "to": s.get("to"), "signed": bool(s.get("sign"))}
               for k, s in v["config"]["steps"].items() if row["status"] in s["from"]]
        return {"version": v["version"], "id": v["id"], "next": nxt,
                "state": v["config"]["states"].get(row["status"], {}).get("label", row["status"])}

    @app.get("/api/quality/ncrs")
    def ncrs(status: str = "active", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        sql = "select * from ncr_records"
        if status == "active":
            sql += " where status not in ('closed', 'cancelled')"
        elif status != "all":
            sql += " where status = %(s)s"
        return [_iso(r) for r in c.execute(sql + " order by id desc limit 500", {"s": status}).fetchall()]

    @app.post("/api/quality/ncrs", status_code=201)
    async def new_ncr(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        keys = ("title", "description", "severity", "owner", "inspection", "item_code", "receipt", "supplier",
                "quantity")
        return ncr_view(c, run(c, lambda: Q.create_ncr(c, u["email"], **{k: d[k] for k in keys if k in d})))

    @app.get("/api/quality/ncrs/{nid}")
    def get_ncr(nid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        try:
            return ncr_view(c, Q.ncr(c, nid))
        except KeyError as exc:
            raise HTTPException(404, "no such report") from exc

    @app.post("/api/quality/ncrs/{nid}/{step}")
    async def ncr_step(nid: int, step: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        pw = str(d.get("password", ""))
        qty = d.get("quantity")
        steps = {
            "update": lambda: Q.update_ncr(c, nid, u["email"], owner=d.get("owner"), severity=d.get("severity")),
            "contain": lambda: Q.contain(c, nid, u["email"], str(d.get("containment", ""))),
            "disposition": lambda: Q.submit_disposition(c, nid, u["email"], str(d.get("disposition", "")),
                                                        None if qty in (None, "") else float(qty),
                                                        str(d.get("reason", ""))),
            "approve": lambda: Q.approve_disposition(c, nid, u, pw),
            "reject-disposition": lambda: Q.reject_disposition(c, nid, u["email"], str(d.get("reason", ""))),
            "close": lambda: Q.close_ncr(c, nid, u, pw, str(d.get("note", ""))),
            "cancel": lambda: Q.cancel_ncr(c, nid, u["email"], str(d.get("reason", ""))),
            "8d": lambda: Q.save_8d(c, nid, u["email"], d.get("sections") or {}),
            "8d-complete": lambda: Q.complete_8d(c, nid, u, pw),
        }
        if step not in steps:
            raise HTTPException(404, f"no step {step}")
        run(c, steps[step])
        return ncr_view(c, Q.ncr(c, nid))

    @app.get("/api/quality/dispositions")
    def dispositions(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return list(Q.disposition_types(c, active_only=False).values())

    @app.post("/api/quality/dispositions")
    async def save_disposition(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        """Disposition types are configuration (ADR-0010): people who change settings maintain them."""
        need(u, "settings:edit")
        d = await body(request)
        return run(c, lambda: Q.save_disposition_type(c, u["email"], str(d.get("code", "")), str(d.get("name", "")),
                                                      bool(d.get("requires_approval")), bool(d.get("active", True))))

    def capa_view(c, row: dict) -> dict:
        return _iso(row) | {"actions": [_iso(a) for a in Q.actions(c, row["id"])], "ncrs": Q.capa_ncrs(c, row["id"]),
                            "history": Q.history(c, "capa", row["id"]),
                            "signatures": Q.signatures(c, "capa", row["id"]), "workflow": wf_brief(c, "capa", row)}

    @app.get("/api/quality/capas")
    def capas(status: str = "active", u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        sql = "select * from capas"
        if status == "active":
            sql += " where status not in ('closed', 'cancelled')"
        elif status != "all":
            sql += " where status = %(s)s"
        return [_iso(r) for r in c.execute(sql + " order by id desc limit 500", {"s": status}).fetchall()]

    @app.post("/api/quality/capas", status_code=201)
    async def new_capa(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:edit")
        d = await body(request)
        ids = d.get("ncr_ids") or ([d["ncr_id"]] if d.get("ncr_id") else [])
        row = run(c, lambda: Q.create_capa(c, u["email"], kind=str(d.get("kind", "corrective")),
                                           title=str(d.get("title", "")), description=str(d.get("description", "")),
                                           ncr_ids=[int(i) for i in ids], owner=d.get("owner"), risk=d.get("risk")))
        return capa_view(c, row)

    @app.get("/api/quality/capas/{cid}")
    def get_capa(cid: int, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        try:
            return capa_view(c, Q.capa(c, cid))
        except KeyError as exc:
            raise HTTPException(404, "no such action") from exc

    @app.post("/api/quality/capas/{cid}/{step}")
    async def capa_step(cid: int, step: str, request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        d = await body(request)
        if step != "action-done":
            need(u, "quality:edit")
        edit = P.allows(u["roles"], "quality:edit")
        today = OA.today(company()[0])
        steps = {
            "update": lambda: Q.update_capa(c, cid, u["email"], **{k: d.get(k) for k in (
                "title", "description", "owner", "risk", "containment", "root_cause")}),
            "link": lambda: Q.link_ncr(c, cid, int(d.get("ncr_id", 0)), u["email"]),
            "submit": lambda: Q.submit_capa(c, cid, u["email"]),
            "plan": lambda: Q.plan_actions(c, cid, u["email"]),
            "action": lambda: Q.add_action(c, cid, u["email"], str(d.get("text", "")), d.get("owner"), d.get("due"),
                                           str(d.get("kind", "corrective")), today),
            "action-done": lambda: Q.action_done(c, int(d.get("action_id", 0)), u["email"], edit,
                                                 str(d.get("evidence", ""))),
            "effectiveness-check": lambda: Q.to_effectiveness(c, cid, u["email"]),
            "effectiveness": lambda: Q.effectiveness(c, cid, u, str(d.get("password", "")), str(d.get("result", "")),
                                                     str(d.get("evidence", ""))),
            "cancel": lambda: Q.cancel_capa(c, cid, u["email"], str(d.get("reason", ""))),
        }
        if step not in steps:
            raise HTTPException(404, f"no step {step}")
        run(c, steps[step])
        return capa_view(c, Q.capa(c, cid))

    @app.get("/api/quality/my-actions")
    def my_actions(u=Depends(user_dep), c=Depends(conn_dep)):
        """Open corrective-action steps assigned to me (anyone may have some)."""
        rows = c.execute("select a.*, c.name as capa, c.title as capa_title from capa_actions a join capas c on "
                         "c.id = a.capa_id where a.owner = %s and not a.done and c.status in ('investigation', "
                         "'implementation') order by a.due nulls last", (u["email"],)).fetchall()
        return [_iso(r) for r in rows]

    @app.get("/api/quality/signatures")
    def all_signatures(u=Depends(user_dep), c=Depends(conn_dep)):
        """Every signature, newest first (append-only)."""
        need(u, "quality:view")
        rows = c.execute("select * from signatures order by id desc limit 1000").fetchall()
        return [_iso(r) for r in rows]

    @app.get("/api/quality/incoming")
    def incoming(u=Depends(user_dep), c=Depends(conn_dep)):
        """Receipts of items to inspect on receipt that have no inspection yet (ADR-0009 item 4)."""
        need(u, "quality:view")
        return IN.awaiting(c)

    @app.post("/api/quality/incoming/draft", status_code=201)
    async def draft_inspection(request: Request, u=Depends(user_dep), c=Depends(conn_dep)):
        """Prepare an ERPNext quality inspection draft for a receipt line; Quality confirms it on the Drafts page."""
        need(u, "quality:edit")
        d = await body(request)
        try:
            size = float(d.get("sample_size"))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "give the sample size you will inspect") from exc
        if size <= 0:
            raise HTTPException(400, "the sample size must be above 0")
        line = next((x for x in IN.awaiting(c) if x["receipt"] == d.get("receipt") and
                     x["item_code"] == d.get("item_code")), None)
        if line is None:
            raise HTTPException(409, "that receipt line is not waiting for inspection")
        payload = {"inspection_type": "Incoming", "reference_type": "Purchase Receipt",
                   "reference_name": line["receipt"], "item_code": line["item_code"], "sample_size": size,
                   "report_date": str(OA.today(company()[0]))}
        try:
            return D.propose(c, u, "Quality Inspection", payload,
                             summary=f"Incoming inspection of {line['item_code']} from {line['receipt']}")
        except D.DraftError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/quality/workflows")
    def workflows(u=Depends(user_dep), c=Depends(conn_dep)):
        """The enabled workflow of each kind of record, in plain words (ADR-0015; read-only in 15a)."""
        need(u, "quality:view")
        out = {}
        for kind, table in W.KINDS.items():
            v = W.ensure(c, kind)
            counts = {r["status"]: r["n"] for r in c.execute(
                f"select status, count(*) as n from {table} group by 1")}  # noqa: S608 - fixed table names
            versions = c.execute("select id, version, status, fingerprint, note, created_by, enabled_by, enabled_at "
                                 "from workflow_versions where kind = %s order by version desc", (kind,)).fetchall()
            out[kind] = {"enabled": _iso({k: v[k] for k in ("id", "version", "fingerprint", "enabled_by", "enabled_at",
                                                              "note")}),
                         "workflow": W.view(v["config"]), "counts": counts, "versions": [_iso(x) for x in versions]}
        return out

    @app.get("/api/quality/suppliers")
    def supplier_quality(days: int = 90, u=Depends(user_dep), c=Depends(conn_dep)):
        """Facts per supplier (ADR-0010): rejection rate, on-time, NCRs, concessions, open corrective actions."""
        need(u, "quality:view")
        if days not in (30, 90, 180, 365):
            raise HTTPException(400, "days must be 30, 90, 180 or 365")
        m = company()[0]
        return IN.supplier_quality(c, OA.today(m), days, m["company"]["timezone"] if m else "UTC")

    @app.get("/api/quality/spc/parameters")
    def spc_parameters(u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return IN.parameters(c)

    @app.get("/api/quality/spc")
    def spc_chart(item_code: str, parameter: str, u=Depends(user_dep), c=Depends(conn_dep)):
        need(u, "quality:view")
        return IN.spc_for(c, item_code, parameter)
