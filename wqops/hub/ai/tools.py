"""The assistant's tools (ADR-0008 item 2): the same reads the web pages use, filtered by the asking person's role.

Each tool returns a dict; objects in it are named ``[Type:Key]`` in ``refs`` so answers can cite them.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from dataclasses import dataclass, field

from wqops.hub import permissions as P
from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import api as OA
from wqops.hub.ont import chain as CH
from wqops.hub.ont import metrics as M
from wqops.hub.ont import schema as S


class ToolError(ValueError):
    pass


@dataclass
class Ctx:
    conn: object
    user: dict
    today: dt.date
    onto: S.Ontology = field(default_factory=S.get)
    rules: dict = field(default_factory=AN.load_rules)
    manifest: dict | None = None
    refs: list[str] = field(default_factory=list)
    run_id: int | None = None
    drafts: list[int] = field(default_factory=list)

    @property
    def roles(self):
        return self.user["roles"]

    def ref(self, t: str, k: str) -> str:
        r = f"[{t}:{k}]"
        if r not in self.refs:
            self.refs.append(r)
        return r

    def need_type(self, t: str) -> None:
        if t not in self.onto.types:
            raise ToolError(f"no object type {t}; types: {', '.join(self.onto.types)}")
        if not self.onto.can_see(self.roles, t):
            raise ToolError(f"this person's role cannot see {self.onto.types[t]['label']} objects")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., dict]

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": {"type": "object", **self.schema}}


def search_objects(ctx: Ctx, query: str, type: str = "", limit: int = 20) -> dict:
    types = [type] if type else [t for t in ctx.onto.types if ctx.onto.can_see(ctx.roles, t)]
    for t in types:
        ctx.need_type(t)
    sql, args = "select type, key, title from ont_objects where not deleted and type = any(%s)", [types]
    for w in query.lower().split():
        sql += " and search like %s"
        args.append(f"%{w.replace('%', '').replace('_', '')}%")
    rows = ctx.conn.execute(sql + " order by type, key limit %s", [*args, max(1, min(int(limit), 50))]).fetchall()
    return {"objects": [{"ref": ctx.ref(r["type"], r["key"]), "title": r["title"]} for r in rows]}


def get_object(ctx: Ctx, type: str, key: str) -> dict:
    ctx.need_type(type)
    r = ctx.conn.execute("select * from ont_objects where type = %s and key = %s", (type, key)).fetchone()
    if r is None:
        raise ToolError(f"no {type} {key}")
    rel = OA.relations(ctx.conn, ctx.onto, ctx.roles, type, key)
    about = ctx.conn.execute(
        "select * from anomalies where status in ('open', 'ack', 'doing') and rule = any(%s) and "
        "((subject_type = %s and subject_key = %s) or related @> %s::jsonb)",
        (AN.visible_rules(ctx.roles, ctx.rules), type, key, json.dumps([[type, key]])),
    ).fetchall()
    return {
        "ref": ctx.ref(type, key),
        "title": r["title"],
        "deleted_in_erpnext": r["deleted"],
        "properties": r["props"],
        "related": [
            {
                "label": g["label"],
                "objects": [ctx.ref(o["type"], o["key"]) + " " + o["title"] for o in g["objects"][:20]],
            }
            for g in rel
        ],
        "open_anomalies": [{"id": a["id"], "title": a["title"], "severity": a["severity"]} for a in about],
    }


def explain(ctx: Ctx, type: str, key: str) -> dict:
    ctx.need_type(type)
    out = OA.visible_chain(ctx.onto, ctx.roles, CH.explain(ctx.conn, type, key, ctx.today))

    def steps(part):
        return [
            {
                "from": ctx.ref(*s["from"]),
                "to": ctx.ref(*s["to"]) if s["to"] else None,
                "relation": s["relation"],
                "why": s["why"],
            }
            for s in out[part]
        ]

    return {"object": ctx.ref(type, key), "causes": steps("causes"), "impact": steps("impact")}


def get_metric(ctx: Ctx, name: str, days: int = 30) -> dict:
    if name not in M.LABELS:
        raise ToolError(f"no metric {name}; metrics: {', '.join(M.LABELS)}")
    if not P.allows(ctx.roles, M.VIEW[name]):
        raise ToolError(f"this person's role cannot see {M.LABELS[name]}")
    if days not in (7, 30, 90):
        raise ToolError("days must be 7, 30 or 90")
    r = M.compute(ctx.conn, name, ctx.today, days)
    for o in r.get("late", []) + r.get("orders", []):
        ctx.ref("SalesOrder", o["key"])
    for i in r.get("items", []):
        ctx.ref("Item", i["item"])
    for q in r.get("inspections", []):
        ctx.ref("QualityInspection", q["key"])
    r.pop("orders", None)  # the late ones are enough; keeps the reply short
    return r | {"as_of": str(ctx.today), "days": days}


def list_anomalies(ctx: Ctx, status: str = "active") -> dict:
    rules = AN.visible_rules(ctx.roles, ctx.rules)
    sql = "select * from anomalies where rule = any(%s)"
    if status == "active":
        sql += " and status in ('open', 'ack', 'doing')"
    rows = ctx.conn.execute(sql + " order by id desc limit 50", (rules,)).fetchall()
    return {
        "anomalies": [
            {
                "id": a["id"],
                "title": a["title"],
                "severity": a["severity"],
                "status": a["status"],
                "rule": ctx.rules[a["rule"]]["name"],
                "detail": a["detail"],
                "about": ctx.ref(a["subject_type"], a["subject_key"]),
            }
            for a in rows
        ]
    }


def get_anomaly(ctx: Ctx, id: int) -> dict:
    a = ctx.conn.execute("select * from anomalies where id = %s", (int(id),)).fetchone()
    if a is None or a["rule"] not in AN.visible_rules(ctx.roles, ctx.rules):
        raise ToolError(f"no anomaly {id} that this person may see")
    pub = AN.public(a, ctx.rules)
    return pub | {
        "about": ctx.ref(a["subject_type"], a["subject_key"]),
        "explain": explain(ctx, a["subject_type"], a["subject_key"]),
    }


TYPE_PROP = {"type": "string", "description": "Object type, e.g. SalesOrder, Item, PurchaseOrder, Supplier"}
READ_TOOLS = [
    Tool(
        "search_objects",
        "Find objects (orders, items, suppliers, customers, receipts, inspections...) by words in "
        "their number, name or item codes.",
        {
            "properties": {"query": {"type": "string"}, "type": TYPE_PROP, "limit": {"type": "integer"}},
            "required": ["query"],
        },
        search_objects,
    ),
    Tool(
        "get_object",
        "Read one object: its properties (orders include their lines), related objects and open anomalies.",
        {"properties": {"type": TYPE_PROP, "key": {"type": "string"}}, "required": ["type", "key"]},
        get_object,
    ),
    Tool(
        "explain",
        "Root causes (upstream) and impact (downstream) of an object, each step with its reason.",
        {"properties": {"type": TYPE_PROP, "key": {"type": "string"}}, "required": ["type", "key"]},
        explain,
    ),
    Tool(
        "get_metric",
        "A metric with its definition and the objects behind it: on_time_delivery, shortages, "
        "inventory_value, days_of_inventory, supplier_on_time, open_nonconformances. A null value means unknown.",
        {
            "properties": {
                "name": {"type": "string", "enum": list(M.LABELS)},
                "days": {"type": "integer", "enum": [7, 30, 90]},
            },
            "required": ["name"],
        },
        get_metric,
    ),
    Tool(
        "list_anomalies",
        "Problems found by the rules (late orders, shortages, late purchase orders, low supplier "
        "on-time, rejected inspections).",
        {"properties": {"status": {"type": "string", "enum": ["active", "all"]}}},
        list_anomalies,
    ),
    Tool(
        "get_anomaly",
        "One anomaly with its suggested action and root-cause chain.",
        {"properties": {"id": {"type": "integer"}}, "required": ["id"]},
        get_anomaly,
    ),
]


def registry(extra: list[Tool] | None = None) -> dict[str, Tool]:
    return {t.name: t for t in READ_TOOLS + (extra or [])}


def call(ctx: Ctx, tools: dict[str, Tool], name: str, args: dict) -> dict:
    if name not in tools:
        raise ToolError(f"no tool {name}")
    try:
        return tools[name].fn(ctx, **(args or {}))
    except TypeError as exc:
        raise ToolError(f"wrong arguments for {name}: {exc}") from exc
