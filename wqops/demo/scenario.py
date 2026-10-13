"""A fictional distribution business over the last 90 days (ADR-0012): a deterministic simulation that lists the
ERPNext documents to create, in date order. Nothing here talks to ERPNext; ``load.py`` writes the list.

All names are invented. Typical problems are built in so the ops hub has something to show: a supplier that is often
late, a key item running out (late and at-risk orders), a purchase order still not delivered, a rejected incoming lot
(moved to QC Hold), and an inspection parameter drifting upwards (control chart signal).
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


@dataclass
class Doc:
    day: dt.date
    kind: str                     # opening | po | receipt | inspection | hold | so | delivery | receipt_draft
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


def build(today: dt.date, seed: int = SEED) -> list[Doc]:  # noqa: PLR0912, PLR0915 - one simulation loop
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
            forced = code == WAITING_ITEM and day == today - dt.timedelta(days=6) and not on_order
            if code == KEY_ITEM and window and on_order:
                continue                                            # waiting on the supplier's promise
            if stock[code] + on_order - demand >= rp and not forced:
                continue
            lead, late_p, (lo_late, hi_late) = SUPPLIERS[i[3]]
            qty = oq * max(1, -(-(rp + demand - stock[code] - on_order) // oq))
            due = day + dt.timedelta(days=lead)
            late = rng.randint(lo_late, hi_late) if rng.random() < late_p else 0
            if forced:
                late = 0                                            # arrives in time to wait for inspection
            if code == KEY_ITEM and window:
                late = 30                                                       # the last bolt orders never come
            ref = nid("P")
            open_pos.append({"ref": ref, "item": code, "qty": qty, "supplier": i[3], "rate": i[4],
                             "arrives": due + dt.timedelta(days=late)})
            docs.append(Doc(day, "po", ref, {"supplier": i[3], "item": code, "qty": qty, "rate": i[4], "due": due}))
    return docs


def summary(docs: list[Doc]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in docs:
        out[d.kind] = out.get(d.kind, 0) + 1
    return out
