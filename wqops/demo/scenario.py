"""A fictional distribution business over the last 90 days (ADR-0012): a deterministic simulation that lists the
ERPNext documents to create, in date order. Nothing here talks to ERPNext; ``load.py`` writes the list.

All names are invented. Typical problems are built in so the ops hub has something to show: a supplier that is often
late, a key item running out (late and at-risk orders), a purchase order still not delivered, a rejected incoming lot
(moved to QC Hold), and an inspection parameter drifting upwards (control chart signal).

Two businesses with the same structure (ADR-0023, step 23e): Harbor Lane Supply in the US (the module's constants)
and Haigang Hardware Supply in China (``ZH``: Chinese names, prices in yuan, numbers of its own). ``activate(manifest)``
switches the module to the one of the company's language; the item codes are the same in both.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field

DAYS = 90
SEED = 20261013

SUPPLIERS = {
    # name: lead days, chance of being late, extra days when late
    "Gulf Fasteners (Demo)": (7, 0.55, (3, 9)),
    "Bayline Electrical (Demo)": (5, 0.10, (1, 2)),
    "Coastal Packaging (Demo)": (4, 0.05, (1, 1)),
    "Summit Tools (Demo)": (10, 0.15, (2, 4)),
}
GULF, BAYLINE, COASTAL, SUMMIT = SUPPLIERS

# code, name, group, supplier, cost, price, mean daily demand (units); reorder point and order size follow from them
ITEMS = [
    ("HX-BOLT-M8", "Hex bolt M8 x 40, zinc (box of 100)", "Fasteners", GULF, 6.40, 11.90, 9),
    ("HX-NUT-M8", "Hex nut M8, zinc (box of 100)", "Fasteners", GULF, 2.10, 4.20, 6),
    ("WSHR-M8", "Flat washer M8 (box of 100)", "Fasteners", GULF, 1.20, 2.60, 5),
    ("SCRW-WD-2", "Wood screw #8 x 2 in (box of 100)", "Fasteners", GULF, 3.30, 6.50, 4),
    ("ANCHOR-38", "Wedge anchor 3/8 in (box of 25)", "Fasteners", GULF, 7.80, 14.50, 2),
    ("CBL-12-50", "Cable 12 AWG, 50 ft", "Electrical", BAYLINE, 18.50, 32.00, 3),
    ("OUTLET-DUP", "Duplex outlet, 15 A", "Electrical", BAYLINE, 1.10, 2.90, 6),
    ("SWITCH-SP", "Single-pole switch", "Electrical", BAYLINE, 0.95, 2.40, 5),
    ("WIRENUT-Y", "Wire connector, yellow (bag of 50)", "Electrical", BAYLINE, 2.70, 5.80, 3),
    ("CONDUIT-34", "EMT conduit 3/4 in, 10 ft", "Electrical", BAYLINE, 6.20, 11.40, 2),
    ("BOX-12", "Shipping box 12 x 12 x 12", "Packaging", COASTAL, 0.85, 1.90, 10),
    ("BOX-18", "Shipping box 18 x 18 x 18", "Packaging", COASTAL, 1.40, 2.95, 6),
    ("TAPE-48", "Packing tape 48 mm (6 rolls)", "Packaging", COASTAL, 5.10, 9.80, 4),
    ("WRAP-20", "Stretch wrap 20 in roll", "Packaging", COASTAL, 14.00, 24.50, 2),
    ("LABEL-4X6", "Shipping labels 4 x 6 (roll of 250)", "Packaging", COASTAL, 4.60, 8.90, 3),
    ("DRILL-BIT-SET", "Drill bit set, 21 pieces", "Tools", SUMMIT, 11.50, 22.00, 1),
    ("TAPE-MEAS-25", "Tape measure 25 ft", "Tools", SUMMIT, 6.80, 13.50, 2),
    ("LEVEL-24", "Level 24 in", "Tools", SUMMIT, 9.40, 18.00, 1),
    ("GLOVE-L", "Work gloves, large (pair)", "Tools", SUMMIT, 2.20, 4.90, 5),
    ("GLASSES-CLR", "Safety glasses, clear", "Tools", SUMMIT, 1.60, 3.80, 4),
]
CUSTOMERS = ["Bayside Hardware (Demo)", "Pelican Builders (Demo)", "Sunline Electric (Demo)", "Mangrove Homes (Demo)",
             "Tidewater Supply (Demo)", "Osprey Contracting (Demo)", "Gulfview Properties (Demo)",
             "Keyline Maintenance (Demo)", "Palmetto Fixtures (Demo)", "Cypress Remodeling (Demo)"]
LINE_QTY = 38                     # mean units per order line; with ~2.2 lines a day each item sells its daily demand
KEY_ITEM = "HX-BOLT-M8"           # runs out at the end; its inspection parameter drifts
INSPECTED = {"HX-BOLT-M8": ("Pitch diameter (mm)", 7.160, 7.212, 7.186, 0.004),
             "CBL-12-50": ("Insulation thickness (mm)", 0.38, 0.52, 0.45, 0.012)}
REQUIRED_BEFORE_RECEIPT = set(INSPECTED)   # ERPNext asks for the inspection before the receipt is submitted
WAITING_ITEM = "CBL-12-50"                  # its last receipt waits for inspection
REJECT_FROM_DAY = 45              # the first bolt lot received from this day on is rejected
DRIFT_FROM_DAY = 55               # bolt pitch diameter drifts upwards from here (still inside the limits)
PEOPLE = {"owner": "dana@demo.example", "ops_manager": "sam@demo.example", "warehouse": "lee@demo.example",
          "purchasing": "pat@demo.example", "sales": "alex@demo.example", "quality": "jordan@demo.example",
          "ai_specialist": "riley@demo.example"}
NAMES = {"dana@demo.example": "Dana Owner", "sam@demo.example": "Sam Ops", "lee@demo.example": "Lee Warehouse",
         "pat@demo.example": "Pat Buyer", "alex@demo.example": "Alex Sales", "jordan@demo.example": "Jordan Quality",
         "riley@demo.example": "Riley AI"}


@dataclass
class Doc:
    day: dt.date
    kind: str                     # opening | po | receipt | inspection | hold | so | delivery | receipt_draft |
    #                               sales_invoice | purchase_invoice | payment_in | payment_out
    ref: str                      # local id, e.g. P007
    data: dict = field(default_factory=dict)


def reorder_point(code: str) -> int:
    i = {x[0]: x for x in ITEMS}[code]
    return i[6] * (SUPPLIERS[i[3]][0] + 3)


def order_qty(code: str) -> int:
    days = 5 if code == KEY_ITEM else 14          # bolts are bought often, so their inspections make a chart
    return {x[0]: x for x in ITEMS}[code][6] * days


def _business(d: dt.date) -> bool:
    return d.weekday() < 5


def build(today: dt.date, seed: int | None = None) -> list[Doc]:  # noqa: PLR0912, PLR0915 - one simulation loop
    seed = SEED if seed is None else seed
    rng = random.Random(seed)  # noqa: S311 - repeatable demo data, not security
    start = today - dt.timedelta(days=DAYS - 1)
    items = {i[0]: i for i in ITEMS}
    docs: list[Doc] = []
    stock = {code: reorder_point(code) + order_qty(code) for code in items}   # opening: reorder point + one order
    docs.append(Doc(start, "opening", "OPEN", {"lines": [{"item": c, "qty": q, "rate": items[c][4]}
                                                       for c, q in stock.items()]}))
    open_pos: list[dict] = []
    open_so: list[dict] = []
    n = {"P": 0, "S": 0, "R": 0, "Q": 0, "D": 0}
    reject_done = False

    def nid(p: str) -> str:
        n[p] += 1
        return f"{p}{n[p]:03d}"

    for k in range(DAYS):
        day = start + dt.timedelta(days=k)
        # 1. goods arrive
        for po in [p for p in open_pos if p["arrives"] == day]:
            open_pos.remove(po)
            code, qty = po["item"], po["qty"]
            if day >= today - dt.timedelta(days=2) and code == WAITING_ITEM:  # waiting for inspection
                docs.append(Doc(day, "receipt_draft", nid("R"), {"po": po["ref"], "item": code, "qty": qty,
                                                                 "supplier": po["supplier"], "rate": po["rate"]}))
                continue
            r = nid("R")
            docs.append(Doc(day, "receipt", r, {"po": po["ref"], "item": code, "qty": qty, "supplier": po["supplier"],
                                                "rate": po["rate"], "inspect_first": code in REQUIRED_BEFORE_RECEIPT}))
            stock[code] += qty
            if code in INSPECTED:
                param, lo, hi, mean, sd = INSPECTED[code]
                rejected = code == KEY_ITEM and not reject_done and k >= REJECT_FROM_DAY
                if code == KEY_ITEM and k >= DRIFT_FROM_DAY:
                    mean += 0.0006 * (k - DRIFT_FROM_DAY)                       # creeping upwards
                values = [round(rng.gauss(mean, sd), 4) for _ in range(5)]
                if rejected:
                    values = [round(hi + 0.006 + i * 0.002, 4) for i in range(5)]  # clearly over the limit
                    reject_done = True
                values = [min(v, hi - 0.0005) if not rejected else v for v in values]
                values = [max(v, lo + 0.0005) for v in values]
                docs.append(Doc(day, "inspection", nid("Q"), {"receipt": r, "item": code, "parameter": param,
                                                             "min": lo, "max": hi, "values": values,
                                                             "rejected": rejected, "sample": 5}))
                if rejected:
                    docs.append(Doc(day, "hold", r + "H", {"item": code, "qty": qty, "rate": po["rate"]}))
                    stock[code] -= qty
        if not _business(day):
            continue
        # 2. orders come in
        for _ in range(rng.choice([1, 1, 2])):
            lines = {}
            for _ in range(rng.choice([1, 2, 2])):
                code = rng.choices(list(items), weights=[i[6] for i in ITEMS])[0]
                lines[code] = lines.get(code, 0) + max(1, round(rng.uniform(0.5, 1.5) * LINE_QTY))
            if day >= today - dt.timedelta(days=12) and KEY_ITEM not in lines and rng.random() < 0.5:
                lines[KEY_ITEM] = LINE_QTY                                       # demand stays high at the end
            so = {"ref": nid("S"), "customer": rng.choice(CUSTOMERS), "day": day,
                  "due": day + dt.timedelta(days=rng.randint(3, 7)),
                  "lines": [{"item": c, "qty": q, "rate": items[c][5], "shipped": False} for c, q in lines.items()]}
            open_so.append(so)
            docs.append(Doc(day, "so", so["ref"], {"customer": so["customer"], "due": so["due"],
                                                   "lines": [{"item": ln["item"], "qty": ln["qty"],
                                                              "rate": ln["rate"]} for ln in so["lines"]]}))
        # 3. ship what can ship (full lines, oldest due first, up to 2 days early)
        for so in sorted(open_so, key=lambda s: (s["due"], s["ref"])):
            if so["due"] - dt.timedelta(days=2) > day:
                continue
            ship = []
            for i, ln in enumerate(so["lines"]):
                if not ln["shipped"] and stock[ln["item"]] >= ln["qty"]:
                    stock[ln["item"]] -= ln["qty"]
                    ln["shipped"] = True
                    ship.append({"line": i, "item": ln["item"], "qty": ln["qty"], "rate": ln["rate"]})
            if ship:
                docs.append(Doc(day, "delivery", nid("D"), {"so": so["ref"], "customer": so["customer"],
                                                            "lines": ship}))
            if all(ln["shipped"] for ln in so["lines"]):
                open_so.remove(so)
        # 4. reorder
        for code, i in items.items():
            on_order = sum(p["qty"] for p in open_pos if p["item"] == code)
            demand = sum(ln["qty"] for s in open_so for ln in s["lines"] if ln["item"] == code and not ln["shipped"])
            rp, oq = reorder_point(code), order_qty(code)
            window = day >= today - dt.timedelta(days=20)
            if code == KEY_ITEM and window and on_order:
                continue                                            # waiting on the supplier's promise
            if stock[code] + on_order - demand >= rp:
                continue
            lead, late_p, (lo_late, hi_late) = SUPPLIERS[i[3]]
            qty = oq * max(1, -(-(rp + demand - stock[code] - on_order) // oq))
            due = day + dt.timedelta(days=lead)
            late = rng.randint(lo_late, hi_late) if rng.random() < late_p else 0
            if code == KEY_ITEM and window:
                late = 30                                                       # the last bolt orders never come
            ref = nid("P")
            open_pos.append({"ref": ref, "item": code, "qty": qty, "supplier": i[3], "rate": i[4],
                             "arrives": due + dt.timedelta(days=late)})
            docs.append(Doc(day, "po", ref, {"supplier": i[3], "item": code, "qty": qty, "rate": i[4], "due": due}))
    # one receipt always waits for inspection at the end, whatever day "today" is (ADR-0012 item 5)
    i = items[WAITING_ITEM]
    lead = SUPPLIERS[i[3]][0]
    ordered, arrived = today - dt.timedelta(days=lead + 1), today - dt.timedelta(days=1)
    ref, qty = nid("P"), order_qty(WAITING_ITEM)
    docs.append(Doc(ordered, "po", ref, {"supplier": i[3], "item": WAITING_ITEM, "qty": qty, "rate": i[4],
                                         "due": arrived}))
    docs.append(Doc(arrived, "receipt_draft", nid("R"), {"po": ref, "item": WAITING_ITEM, "qty": qty,
                                                         "supplier": i[3], "rate": i[4]}))
    docs += billing(docs, today, seed)
    docs.sort(key=lambda d: (d.day, d.kind != "opening"))      # stable: same-day documents keep their order
    return docs


TERMS_DAYS = 30
BILLING = ("sales_invoice", "purchase_invoice", "payment_in", "payment_out")
SLOW_PAYER = "Osprey Contracting (Demo)"   # pays late: overdue receivables to show (ADR-0018)


def billing(docs: list[Doc], today: dt.date, seed: int | None = None) -> list[Doc]:
    """Invoices for every delivery and every submitted receipt (30 days' terms), and the payments made by today.

    Its own random numbers, so the goods simulation above stays exactly as it was. Most customers pay within a few
    days of the due date; one pays late; the business pays its suppliers on the due date.
    """
    rng = random.Random((SEED if seed is None else seed) + 18)  # noqa: S311 - a reproducible simulation, not security
    out: list[Doc] = []
    for d in [x for x in docs if x.kind in ("delivery", "receipt")]:
        due = d.day + dt.timedelta(days=TERMS_DAYS)
        if d.kind == "delivery":
            ref = d.ref + "I"
            out.append(Doc(d.day, "sales_invoice", ref, {"delivery": d.ref, "customer": d.data["customer"],
                                                         "lines": d.data["lines"], "due": due}))
            pay = due + dt.timedelta(days=rng.randint(15, 30) if d.data["customer"] == SLOW_PAYER
                                     else rng.randint(-5, 6))
            if pay < today:
                out.append(Doc(pay, "payment_in", ref + "P", {"invoice": ref}))
        else:
            ref = d.ref + "I"
            out.append(Doc(d.day, "purchase_invoice", ref, {"receipt": d.ref, "supplier": d.data["supplier"],
                                                            "item": d.data["item"], "qty": d.data["qty"],
                                                            "rate": d.data["rate"], "due": due}))
            if due < today:
                out.append(Doc(due, "payment_out", ref + "P", {"invoice": ref}))
    return out


def summary(docs: list[Doc]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in docs:
        out[d.kind] = out.get(d.kind, 0) + 1
    return out


# ---------------------------------------------------------------- the business in China (ADR-0023, step 23e)

_ZH_SUP = {
    "海湾紧固件（演示）": (6, 0.5, (3, 8)),
    "滨海电气（演示）": (4, 0.10, (1, 2)),
    "沿海包装（演示）": (3, 0.05, (1, 1)),
    "峰顶工具（演示）": (9, 0.15, (2, 4)),
}
_ZG, _ZB, _ZC, _ZS = _ZH_SUP
ZH = {
    "SEED": 20261056,          # chosen so that late sales orders show on any day, like the US business
    "SUPPLIERS": _ZH_SUP,
    "ITEMS": [
        ("HX-BOLT-M8", "六角螺栓 M8×40 镀锌（100 只/盒）", "紧固件", _ZG, 38.00, 68.00, 10),
        ("HX-NUT-M8", "六角螺母 M8 镀锌（100 只/盒）", "紧固件", _ZG, 12.50, 24.00, 7),
        ("WSHR-M8", "平垫圈 M8（100 只/盒）", "紧固件", _ZG, 7.20, 15.00, 5),
        ("SCRW-WD-2", "自攻木螺钉 4×50（100 只/盒）", "紧固件", _ZG, 18.00, 36.00, 4),
        ("ANCHOR-38", "膨胀螺栓 M10×100（25 只/盒）", "紧固件", _ZG, 45.00, 85.00, 2),
        ("CBL-12-50", "BV 2.5 平方电线（100 米/卷）", "电气", _ZB, 168.00, 258.00, 3),
        ("OUTLET-DUP", "五孔插座 10 A", "电气", _ZB, 6.50, 16.00, 6),
        ("SWITCH-SP", "单控开关", "电气", _ZB, 5.20, 13.00, 5),
        ("WIRENUT-Y", "接线端子 黄色（50 只/袋）", "电气", _ZB, 15.00, 32.00, 3),
        ("CONDUIT-34", "PVC 线管 20 mm（3 米）", "电气", _ZB, 8.60, 16.00, 2),
        ("BOX-12", "纸箱 30×30×30 cm", "包装", _ZC, 4.80, 9.50, 11),
        ("BOX-18", "纸箱 45×45×45 cm", "包装", _ZC, 7.90, 15.00, 6),
        ("TAPE-48", "封箱胶带 48 mm（6 卷）", "包装", _ZC, 22.00, 42.00, 4),
        ("WRAP-20", "缠绕膜 50 cm（卷）", "包装", _ZC, 65.00, 118.00, 2),
        ("LABEL-4X6", "快递面单 100×150（500 张/卷）", "包装", _ZC, 21.00, 39.00, 3),
        ("DRILL-BIT-SET", "麻花钻套装（21 支）", "工具", _ZS, 52.00, 98.00, 1),
        ("TAPE-MEAS-25", "钢卷尺 7.5 米", "工具", _ZS, 24.00, 46.00, 2),
        ("LEVEL-24", "水平尺 60 cm", "工具", _ZS, 38.00, 72.00, 1),
        ("GLOVE-L", "劳保手套 大号（双）", "工具", _ZS, 6.00, 13.50, 6),
        ("GLASSES-CLR", "防护眼镜 透明", "工具", _ZS, 7.50, 16.00, 4),
    ],
    "CUSTOMERS": ["湾畔五金（演示）", "海鸥建筑（演示）", "阳光电工（演示）", "红树林家居（演示）", "潮汐建材（演示）",
                  "鱼鹰装饰工程（演示）", "海景物业（演示）", "基线维修（演示）", "棕榈装修配件（演示）",
                  "柏木装修（演示）"],
    "LINE_QTY": 40,
    "INSPECTED": {"HX-BOLT-M8": ("中径（mm）", 7.160, 7.212, 7.186, 0.004),
                  "CBL-12-50": ("绝缘厚度（mm）", 0.70, 0.90, 0.80, 0.02)},
    "SLOW_PAYER": "鱼鹰装饰工程（演示）",
}
ZH["GULF"], ZH["BAYLINE"], ZH["COASTAL"], ZH["SUMMIT"] = _ZG, _ZB, _ZC, _ZS

_NAMES = ("SEED", "SUPPLIERS", "ITEMS", "CUSTOMERS", "LINE_QTY", "INSPECTED", "SLOW_PAYER", "GULF", "BAYLINE",
          "COASTAL", "SUMMIT")
EN = {k: globals()[k] for k in _NAMES}
EN.update(PEOPLE=dict(PEOPLE), NAMES=dict(NAMES))


def activate(manifest: dict | None) -> str:
    """Switch the module to the business of the company's language ('en' or 'zh'); the people come from the manifest
    (by role), so the demo records are made by the company's own demo people. Returns the language."""
    lang = ((manifest or {}).get("company") or {}).get("language") or "en"
    prof = ZH if lang == "zh" else EN
    g = globals()
    for k in _NAMES:
        g[k] = prof[k]
    g["REQUIRED_BEFORE_RECEIPT"] = set(prof["INSPECTED"])
    people, names = dict(EN["PEOPLE"]), dict(EN["NAMES"])
    if manifest and manifest.get("people"):
        people, names = {}, {}
        for p in manifest["people"]:
            for r in p.get("roles") or ():
                people.setdefault(r, p["email"])
            names[p["email"]] = p["name"]
    g["PEOPLE"], g["NAMES"] = people, names
    return lang
