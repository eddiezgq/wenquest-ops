"""The fictional sewing machine demo company (PLM step 26f, ADR-0026): 蓝湾缝纫机械（演示）.

    python -m wqops.demo.load         # with a company manifest that says demo_story: sewing

Everything is invented: the company, its people, suppliers, dealers, both machines and every number. What it loads:

1. PLM: the parts and assemblies of a lockstitch machine (WQ-8800D, 347 part codes) and an overlock machine (WQ-737),
   with their option modules, come in as one design data batch and are written by an engineer; the parts get typical
   parameters and are released, the BOMs released bottom up (each makes its ERPNext BOM, which the installer submits,
   standing in for the person who submits it in ERPNext); the bought parts get approved suppliers first. Both base
   machines get a model configuration; four lockstitch and two overlock models are generated and released.
2. ERPNext, about 90 days (deterministic): opening stock, purchases and receipts of the rotary hook with incoming
   inspections, work orders made and finished, sales orders to dealers and their deliveries; a few left open.
3. The story (round 109 section 十五): the hook supplier changed the hook's material; the lots after the change are
   softer at the point (still inside the limits); two dealers complain of broken thread; a corrective action is open
   with the root cause written. Whoever looks at the demo starts the design change from there. A finished design
   change (needle plate A to B) and a FreeCAD batch waiting in the design data inbox are there as well.
4. The parts manual (rounds 124, 135): every lockstitch part in 3D (FreeCAD), exploded views, English names, and
   edition 1 of one lockstitch model's manual (sewing_manual.py).

Plain code, no AI, no network beyond ERPNext. The texts are the company's (Chinese); this company has no English
version yet. Signatures are accepted without passwords while it runs (demo_signing, demo companies only).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal

from wqops.demo import sewing_manual as SM
from wqops.demo.machines import lockstitch as LS
from wqops.demo.machines import overlock as OL
from wqops.erp import ErpClient, ErpError
from wqops.erp_setup import fiscal_year, warehouse_name

DAYS = 90
SIGN = "demo-installer"

# people of companies/demo-sewing.yaml by role; the second engineer approves what the first one edits
OWNER, OPS, WAREHOUSE, BUYER, SALES, QA = ("linhai@demo.example", "wujian@demo.example", "zhengtao@demo.example",
                                           "hefang@demo.example", "huangwei@demo.example", "xujing@demo.example")
ENG, ENG2 = "caiming@demo.example", "yeqing@demo.example"

HOOK = "WQ88-1711"                       # 旋梭 HSH-7.94A: the part of the story
HOOK_SUPPLIER = "宁波精密旋梭（演示）"
NEEDLE_PLATE = "WQ88-1812"               # 针板: the finished design change, A to B
MANUAL_MODEL = "5TA"                     # the lockstitch model with a ready parts manual (round 124, 27d)

# supplier of each bought part: the first rule whose words are in the part's name (else the standard parts maker)
SUPPLIERS = [
    (HOOK_SUPPLIER, ("旋梭", "梭芯")),
    ("东阳机针（演示）", ("机针",)),
    ("台州智控电机（演示）", ("电机", "控制箱", "操作面板", "脚踏", "传感器", "电磁铁", "线束", "电源线", "接地线",
                            "开关", "照明灯")),
    ("华东轴承（演示）", ("轴承",)),
    ("海曙传动件（演示）", ("同步带", "油管")),
    ("椒江包装印务（演示）", ("包装", "说明书", "合格证", "图册", "附件袋", "泡沫", "防尘罩", "油壶", "螺丝刀",
                            "扳手", "机油", "镊子")),
    ("温岭标准件（演示）", ()),
]
DEALERS = ["东莞衣联缝纫设备（演示）", "杭州织锦服装机械（演示）", "泉州鞋服机械（演示）", "郑州中原缝制设备（演示）",
           "宁波海缝设备（演示）", "越南西贡缝纫设备（演示）", "达卡制衣机械（演示）", "义乌小商品缝纫（演示）"]

# models: choice -> (name suffix shown in the story, price in yuan)
LS_PRICE = {"5TA": 3980, "7TA": 4180, "5TK": 3680, "5NK": 3180}
OL_PRICE = {"4": 3280, "5": 3880}

# (day, model choice, quantity): lockstitch work orders finished on that day; the hook is used once per machine
LS_RUNS = [(6, "5TA", 20), (13, "7TA", 20), (20, "5TA", 20), (27, "5TK", 20), (34, "5TA", 20), (41, "5NK", 20),
           (48, "7TA", 20), (55, "5TA", 20), (62, "5TK", 20), (69, "7TA", 20), (76, "5TA", 20), (83, "5NK", 20)]
OL_RUNS = [(9, "4", 20), (23, "5", 20), (37, "4", 20), (51, "4", 20), (65, "5", 20), (79, "4", 20)]
LS_OPEN = [(86, "5TA", 20), (88, "7TA", 20)]            # work orders not started yet
HOOK_OPENING = 100
HOOK_LOTS = [(10, 80, False), (35, 60, False), (60, 60, True), (78, 60, True)]   # day, qty, after the material change
HOOK_OPEN_PO = [(82, 60, 92), (86, 60, 99)]              # ordered on, qty, due (days from the start)
MATERIAL_CHANGE_DAY = 52
HARDNESS = ("梭尖硬度 (HRC)", 58.0, 62.0)                 # parameter, lower and upper limit


class SewingError(RuntimeError):
    pass


# ---------------------------------------------------------------- the machines as data

def _walk(node, out: dict, links: dict) -> None:
    code, name, _qty, src, unit, kids = node
    if code in out and kids:
        return                       # an assembly used in two places (1850 in both feed assemblies): its lines once
    if code not in out:
        out[code] = {"key": code, "code": code, "name": name, "uom": unit, "source": "make" if src == "自制" else "buy"}
    for k in kids:
        links[(code, k[0])] += Decimal(str(k[2]))
        _walk(k, out, links)


def design_data() -> dict:
    """Both machines and their option modules as one design data batch (nodes and links)."""
    nodes, links = {}, defaultdict(Decimal)
    for t in (LS.TREE, *LS.OPTION_PARTS, OL.TREE, *OL.OPTION_PARTS):
        _walk(t, nodes, links)
    return {"nodes": list(nodes.values()),
            "links": [{"parent": p, "child": c, "qty": format(q.normalize(), "f")} for (p, c), q in links.items()]}


def _children(data: dict) -> dict[str, dict[str, Decimal]]:
    out = defaultdict(lambda: defaultdict(Decimal))
    for ln in data["links"]:
        out[ln["parent"]][ln["child"]] += Decimal(ln["qty"])
    return out


def model_lines(base: str, config: dict, choice: dict, kids: dict) -> dict[str, Decimal]:
    """The model's own BOM lines: the base machine's lines with the chosen options' changes (as 26c composes it)."""
    lines = dict(kids[base])
    for gcode, _name, options in config["groups"]:
        _oc, _on, edits = next(o for o in options if o[0] == choice[gcode])
        for act, code, with_, qty in edits:
            if act == "remove":
                del lines[code]
            elif act == "replace":
                q = lines.pop(code)
                lines[with_] = lines.get(with_, Decimal(0)) + (Decimal(str(qty)) if qty else q)
            else:
                lines[code] = lines.get(code, Decimal(0)) + Decimal(str(qty))
    return lines


def explode(lines: dict[str, Decimal], kids: dict) -> dict[str, Decimal]:
    """Leaf parts for one machine with these top lines."""
    out = defaultdict(Decimal)
    stack = list(lines.items())
    while stack:
        code, q = stack.pop()
        if kids.get(code):
            stack.extend((c, q * cq) for c, cq in kids[code].items())
        else:
            out[code] += q
    return out


def supplier_of(name: str) -> str:
    return next((s for s, words in SUPPLIERS if any(w in name for w in words)), SUPPLIERS[-1][0])


def _h(code: str, n: int) -> int:
    return int(hashlib.sha256(code.encode()).hexdigest()[:8], 16) % n


MACHINES = {"WQ88-0000": ("WQ-8800D", "电脑直驱单针平缝机，自动剪线、自动抬压脚、自动倒缝（演示）"),
            "WQ73-0000": ("WQ-737", "电脑直驱四线包缝机，差动送布（演示）")}

BEARINGS = {"6202ZZ": (15, 35, 11), "6201ZZ": (12, 32, 10), "6200ZZ": (10, 30, 9), "6000ZZ": (10, 26, 8),
            "6001ZZ": (12, 28, 8), "608ZZ": (8, 22, 7), "HK0810": (8, 12, 10), "HK1012": (10, 14, 12),
            "HK1210": (12, 16, 10), "HK0608": (6, 10, 8), "NA4900": (10, 22, 13)}


def params(category: str, code: str, name: str) -> dict:  # noqa: PLR0911, PLR0912 - one category after another
    """Typical values for the demo (invented, not from a drawing): enough for the release checks and the look-alike
    search to have something to work on."""
    h = _h(code, 1000)
    if category == "shaft":
        return {"d": 8 + h % 12, "length": 60 + h % 300, "material": "45 钢", "heat_treatment": "调质 + 高频淬火"}
    if category == "bushing":
        return {"load": 400 + h % 800, "d_in": 8 + h % 10, "d_out": 14 + h % 10, "length": 12 + h % 20}
    if category == "bearing":
        spec = name.rsplit(maxsplit=1)[-1]
        d, big_d, b = BEARINGS.get(spec, (10, 26, 8))
        return {"designation": spec, "d": d, "D": big_d, "B": b}
    if category == "fastener":
        return {"spec": " ".join(name.split()[1:]) or name, "standard": "企业标准（演示）", "grade": "8.8"}
    if category == "link":
        return {"L": 20 + h % 60, "d1": 8 + h % 6, "d2": 5 + h % 4, "t": 5 + h % 6, "material": "QT500-7"}
    if category == "cam":
        return {"base_r": 12 + h % 10, "lift": 2 + h % 4, "material": "20CrMnTi"}
    if category == "pulley":
        return {"r": 18 + h % 10, "teeth": 30 + h % 10, "width": 10, "bore": 14 + h % 6}
    if category == "belt":
        return {"EA": 120, "width": 10, "pitch": 3}
    if category == "hook":
        return {"model": name.rsplit(maxsplit=1)[-1], "bobbin_d": 21.2, "max_spm": 5000, "material": "SUJ2"}
    if category == "feeddog":
        return {"rows": 3 if "厚料" not in name else 2, "pitch": 1.2 if "厚料" not in name else 1.6, "length": 22,
                "material": "20CrMnTi"}
    if category == "needle":
        nm = 90 if "#14" in name else 75
        return {"nm": nm, "blade_d": nm / 100, "shank_d": 1.62 if "DB" in name else 2.0, "length": 33.4}
    if category == "needlebar":
        return {"mass": 0.06, "d": 8, "length": 160}
    if category == "motor":
        w = 550 if "550" in name else 400
        return {"power_w": w, "rated_nm": 1.8 if w == 550 else 1.3, "peak_nm": 5.4 if w == 550 else 3.9,
                "rated_rpm": 3000, "max_rpm": 5000, "inertia": 1.2, "flange": 80, "length": 95, "shaft_d": 14}
    if category == "electronic":
        return {"spec": " ".join(name.split()[1:]) or name, "maker_part": f"DEMO-{code}"}
    if category == "frame":
        return {"mass": 3 + h % 30, "material": "HT250"}
    if category == "assembly" and code in MACHINES:
        return {"model": MACHINES[code][0], "description_short": MACHINES[code][1]}
    if category == "other":
        return {"spec": " ".join(name.split()[1:]) or "", "material": "按图纸（演示）"}
    return {}


def cost(category: str, source: str, code: str, name: str) -> float:  # noqa: PLR0911
    """Unit cost in yuan (invented)."""
    h = _h(code, 100)
    if category == "fastener":
        return round(0.05 + h / 500, 2)
    if category == "bearing":
        return round(4 + h / 10, 2)
    if category == "motor":
        return 620.0 if "550" in name else 520.0
    if category == "electronic":
        return 260.0 if "控制箱" in name else round(18 + h, 2)
    if category == "hook":
        return 46.0
    if category == "needle":
        return 0.9
    if category == "frame":
        return round(60 + h * 2, 2)
    if source == "buy":
        return round(2 + h / 4, 2)
    return round(3 + h / 2, 2)


# ---------------------------------------------------------------- the loader

class Sewing:
    def __init__(self, conn, erp: ErpClient, manifest: dict, today: dt.date, say: Callable[[str], None] = print):
        if not manifest.get("demo") or manifest.get("demo_story") != "sewing":
            raise SewingError("the sewing demo loads only into a manifest with demo: true and demo_story: sewing")
        self.conn, self.erp, self.m, self.today, self.say = conn, erp, manifest, today, say
        self.start = today - dt.timedelta(days=DAYS - 1)
        self.company = manifest["company"]["name"]
        whs = {w["kind"]: warehouse_name(manifest, w) for w in manifest["warehouses"]}
        self.main, self.hold = whs["stores"], whs.get("quarantine")
        self.data = design_data()
        self.kids = _children(self.data)
        self.nodes = {n["key"]: n for n in self.data["nodes"]}
        self.out: dict = {}

    def day(self, n: int) -> dt.date:
        return self.start + dt.timedelta(days=n)

    def u(self, email: str) -> dict:
        from wqops.hub import accounts as Acc  # noqa: PLC0415

        x = Acc.get(self.conn, email)
        if x is None:
            raise SewingError(f"{email} is not a person of the company")
        return x

    # ---- ERPNext writes, tried again on a deadlock (as the distribution demo does)
    def _again(self, fn):
        from wqops.demo.load import Loader  # noqa: PLC0415

        return Loader._again(fn)

    def make(self, doc: dict, submit: bool = True) -> dict:
        out = self._again(lambda: self.erp.insert(doc))
        if submit:
            self._again(lambda: self.erp.update(doc["doctype"], out["name"], {"docstatus": 1}))
        return out

    # ---- 1. ERPNext masters
    def masters(self) -> None:
        from wqops.demo.load import _leaf  # noqa: PLC0415

        if self.erp.find("Customer", {"customer_name": DEALERS[0]}):
            raise SewingError("the sewing demo is already loaded (its dealers exist)")
        fy_start, fy_end = fiscal_year(self.m["company"]["fiscal_year_start"], self.start)
        if not self.erp.list("Fiscal Year", filters=[["year_start_date", "<=", str(self.start)],
                                                     ["year_end_date", ">=", str(self.start)]], limit=1):
            self.erp.insert({"doctype": "Fiscal Year", "year": f"{fy_start.year}-{fy_end.year}"
                             if fy_start.year != fy_end.year else str(fy_start.year),
                             "year_start_date": str(fy_start), "year_end_date": str(fy_end),
                             "companies": [{"company": self.company}]})
        rows = self.erp.list("Stock Entry Type", filters=[["purpose", "=", "Material Receipt"]], limit=5)
        names = [r["name"] for r in rows]
        self.receipt_type = "Material Receipt" if "Material Receipt" in names or not names else names[0]
        sgroup, cgroup, territory = _leaf(self.erp, "Supplier Group"), _leaf(self.erp, "Customer Group"), \
            _leaf(self.erp, "Territory")
        for s, _words in SUPPLIERS:
            self.erp.insert({"doctype": "Supplier", "supplier_name": s, "supplier_group": sgroup})
        for c in DEALERS:
            self.erp.insert({"doctype": "Customer", "customer_name": c, "customer_group": cgroup,
                             "territory": territory})
        if self.erp.get("Quality Inspection Parameter", HARDNESS[0]) is None:
            self.erp.insert({"doctype": "Quality Inspection Parameter", "parameter": HARDNESS[0]})

    # ---- 2. PLM: parts and assemblies in, released
    def parts(self) -> None:
        from wqops.hub.plm import intake as IN  # noqa: PLC0415

        eng = self.u(ENG)
        v = IN.receive(self.conn, source="excel", sent_by=ENG, data=self.data,
                       file_name="蓝湾旧BOM-平缝机与包缝机.xlsx")
        bad = IN.problems(self.conn, IN._get(self.conn, v["id"]), self.erp)
        if bad:
            raise SewingError("design data not ready: " + "; ".join(bad[:5]))
        v = IN.write(self.conn, eng, v["id"], SIGN, self.erp)
        failed = self.conn.execute("select item_code from plm_parts where erp_state = 'failed'").fetchall()
        if failed:
            raise SewingError("ERPNext items not made: " + ", ".join(r["item_code"] for r in failed[:10]))
        self.out["parts"] = len(v["result"]["parts_made"])
        # costs for stock, BOM costing and the sales prices of the machines (ERPNext items)
        for p in self.conn.execute("select item_code, name, category, source from plm_parts"):
            if not self.kids.get(p["item_code"]):
                c = cost(p["category"], p["source"], p["item_code"], p["name"])
                self._again(lambda p=p, c=c: self.erp.update("Item", p["item_code"], {"valuation_rate": c}))
        # every hook lot is inspected at receiving (the hardness of the point)
        self._again(lambda: self.erp.update("Item", HOOK, {"inspection_required_before_purchase": 1}))
        self.say(f"{self.out['parts']} parts written")
        # every part in 3D (FreeCAD, round 135 33a), onto the draft parts, with where each use sits
        self.out["models_3d"] = SM.models(self.conn, self.u(ENG))

    def suppliers(self) -> None:
        """Every bought part has an approved supplier (the BOM release checks it)."""
        from wqops.hub.quality import asl as ASL  # noqa: PLC0415

        self.sync()
        owner = self.u(OWNER)
        n = 0
        for p in self.conn.execute("select item_code, name from plm_parts where source = 'buy' order by item_code"):
            sup = supplier_of(p["name"])
            risk = "medium" if sup == HOOK_SUPPLIER else "low"
            e = ASL.add(self.conn, QA, sup, p["item_code"],
                        {"risk": risk, "basis": "样品检验合格，质量体系证书在档（演示）"})
            ASL.approve(self.conn, owner, e["id"], SIGN, reason="按《供应商评价程序》评价合格（演示）",
                        today=self.today,
                        review_due=str(self.today + dt.timedelta(days=365)))
            n += 1
        self.out["approved_suppliers"] = n

    def release(self) -> None:
        from wqops.hub.plm import boms as B  # noqa: PLC0415
        from wqops.hub.plm import catalog as CAT  # noqa: PLC0415
        from wqops.hub.plm import parts as PT  # noqa: PLC0415

        eng = self.u(ENG)
        for p in self.conn.execute("select id, item_code, name, category from plm_parts where status = 'draft' "
                                   "order by item_code").fetchall():
            ps = {k: v for k, v in params(p["category"], p["item_code"], p["name"]).items()
                  if k in {f["key"] for f in CAT.get(p["category"])["fields"]} and v not in ("", None)}
            if ps:
                PT.update(self.conn, eng, p["id"], {"params": {**(PT.current(self.conn, p["id"])["params"] or {}),
                                                               **ps}})
            PT.release(self.conn, eng, p["id"], SIGN)
        # BOMs from the bottom up; each makes its ERPNext BOM, submitted here
        depth = {}

        def d(code):
            if code not in depth:
                depth[code] = 1 + max((d(c) for c in self.kids.get(code, {})), default=0)
            return depth[code]
        boms = self.conn.execute("select b.id, p.item_code from plm_boms b join plm_parts p on p.id = b.part_id "
                                 "where b.status = 'draft'").fetchall()
        for b in sorted(boms, key=lambda r: (d(r["item_code"]), r["item_code"])):
            self._release_bom(B, eng, b["id"])
        self.out["boms"] = len(boms)
        self.say(f"{len(boms)} BOMs released")

    def _release_bom(self, B, user: dict, bid: int) -> None:
        v = B.release(self.conn, user, bid, SIGN, self.erp)
        name = v["bom"].get("erp_bom")
        if not name:
            raise SewingError(f"BOM {bid}: no ERPNext BOM ({v['bom'].get('erp_error')})")
        self._again(lambda: self.erp.update("BOM", name, {"docstatus": 1}))

    def models(self) -> None:
        from wqops.hub.plm import boms as B  # noqa: PLC0415
        from wqops.hub.plm import config as CFG  # noqa: PLC0415
        from wqops.hub.plm import parts as PT  # noqa: PLC0415

        eng = self.u(ENG)
        self.model_codes = {}
        for machine, cfg, prices in ((LS, LS.CONFIG, LS_PRICE), (OL, OL.CONFIG, OL_PRICE)):
            base = PT.by_code(self.conn, machine.TREE[0])
            data = {"groups": [{"code": g, "name": n, "options": [
                {"code": oc, "name": on, "edits": [{"action": a, "code": c, "with": w, "qty": q}
                                                   for a, c, w, q in edits]} for oc, on, edits in opts]}
                for g, n, opts in cfg["groups"]],
                "rules": [{"kind": k, "a": a, "b": b} for k, a, b in cfg["rules"]],
                "version": CFG.version(self.conn, base["id"])}
            CFG.save(self.conn, eng, base["id"], data)
            for choice in cfg["models"]:
                key = "".join(choice[g] for g, _n, _o in cfg["groups"])
                v = CFG.generate(self.conn, eng, base["id"], choice, self.erp, CFG.version(self.conn, base["id"]))
                pid = v["model"]
                PT.release(self.conn, eng, pid, SIGN)
                self._release_bom(B, eng, v["bom"])
                code = PT.get(self.conn, pid)["item_code"]
                self._again(lambda c=code, k=key, pr=prices: self.erp.update("Item", c, {"standard_rate": pr[k]}))
                self.model_codes[(machine.TREE[0], key)] = code
        self.out["models"] = sorted(self.model_codes.values())

    # ---- 3. the business in ERPNext
    def business(self) -> None:
        rates = {r["item_code"]: float(r.get("valuation_rate") or 0) for r in self.erp.list(
            "Item", fields=["item_code", "valuation_rate"], limit=0)}
        # what the finished and the open work orders need, plus a buffer; the hook has its own flow
        need = defaultdict(Decimal)
        runs = [(LS, LS.CONFIG, day, k, q) for day, k, q in LS_RUNS] + [(OL, OL.CONFIG, day, k, q)
                                                                       for day, k, q in OL_RUNS]
        opens = [(LS, LS.CONFIG, day, k, q) for day, k, q in LS_OPEN]
        for machine, cfg, _day, key, q in runs + opens:
            choice = dict(zip([g for g, _n, _o in cfg["groups"]], key, strict=True))
            for code, n in explode(model_lines(machine.TREE[0], cfg, choice, self.kids), self.kids).items():
                need[code] += n * q
        lines = []
        for code, n in sorted(need.items()):
            if code == HOOK:
                continue
            qty = int(n * Decimal("1.15")) + 5
            lines.append({"item_code": code, "qty": qty, "t_warehouse": self.main, "basic_rate": rates.get(code) or 1})
        lines.append({"item_code": HOOK, "qty": HOOK_OPENING, "t_warehouse": self.main,
                      "basic_rate": rates.get(HOOK) or 46})
        events = [(0, 0, "opening", lines)]
        for day, qty, after in HOOK_LOTS:
            events.append((day - 7, 1, "hook_po", (qty, day)))
            events.append((day, 2, "hook_receipt", (qty, after)))
        for day, qty, due in HOOK_OPEN_PO:
            events.append((day, 1, "hook_po", (qty, due)))
        for machine, _cfg, day, key, q in runs:
            events.append((day - 5, 3, "so", (machine, key, q, day + 2)))
            events.append((day, 4, "wo_done", (machine, key, q)))
            events.append((day + 2, 5, "deliver", (machine, key)))
        for machine, _cfg, day, key, q in opens:
            events.append((day, 4, "wo_open", (machine, key, q)))
        for i, (machine, key, q) in enumerate([(LS, "5TA", 10), (LS, "7TA", 10), (LS, "5NK", 8)]):
            events.append((84 + i * 2, 3, "so_open", (machine, key, q, 97 + i * 3)))
        self.sos: dict = {}
        pending = defaultdict(list)       # model code -> sales orders waiting to be delivered
        self.out["documents"] = defaultdict(int)
        for n, (day, _order, kind, x) in enumerate(sorted(events, key=lambda e: (e[0], e[1]))):
            self._event(self.day(day), kind, x, rates, pending)
            self.out["documents"][kind] += 1
            if n % 20 == 0:
                self.say(f"{n} of {len(events)} business events")
        self.out["documents"] = dict(self.out["documents"])

    def _model(self, machine, key) -> str:
        return self.model_codes[(machine.TREE[0], key)]

    def _event(self, day: dt.date, kind: str, x, rates: dict, pending: dict) -> None:
        posting = {"posting_date": str(day), "set_posting_time": 1}
        if kind == "opening":
            self.make({"doctype": "Stock Entry", "stock_entry_type": self.receipt_type, "company": self.company,
                       **posting, "remarks": "期初库存（演示）", "items": x})
        elif kind == "hook_po":
            qty, due = x
            po = self.make({"doctype": "Purchase Order", "supplier": HOOK_SUPPLIER, "company": self.company,
                            "transaction_date": str(day), "schedule_date": str(self.day(due)),
                            "items": [{"item_code": HOOK, "qty": qty, "rate": 46, "warehouse": self.main,
                                       "schedule_date": str(self.day(due))}]})
            self.hook_pos = [*getattr(self, "hook_pos", []), po]
        elif kind == "hook_receipt":
            qty, after = x
            po = next(p for p in self.hook_pos if p["items"][0]["qty"] == qty and not p.get("_received"))
            po["_received"] = True
            pr = self.make({"doctype": "Purchase Receipt", "supplier": HOOK_SUPPLIER, "company": self.company,
                            **posting, "items": [{"item_code": HOOK, "qty": qty, "rate": 46, "warehouse": self.main,
                                                  "purchase_order": po["name"],
                                                  "purchase_order_item": po["items"][0]["name"]}]}, submit=False)
            base, spread = (58.6, 0.25) if after else (60.6, 0.3)
            vals = [round(base + spread * ((_h(f"{pr['name']}{i}", 21) - 10) / 10), 1) for i in range(5)]
            self.make({"doctype": "Quality Inspection", "inspection_type": "Incoming",
                       "reference_type": "Purchase Receipt", "reference_name": pr["name"], "item_code": HOOK,
                       "sample_size": 5, "report_date": str(day), "inspected_by": "Administrator",
                       "remarks": "换料后批次（演示）" if after else "",
                       "readings": [{"specification": HARDNESS[0], "numeric": 1, "min_value": HARDNESS[1],
                                     "max_value": HARDNESS[2],
                                     **{f"reading_{i}": str(v) for i, v in enumerate(vals, start=1)}}]})
            self._again(lambda: self.erp.update("Purchase Receipt", pr["name"], {"docstatus": 1}))
        elif kind in ("so", "so_open"):
            machine, key, q, due = x
            code = self._model(machine, key)
            dealer = DEALERS[_h(f"{code}{day}", len(DEALERS))]
            if kind == "so_open":
                dealer = DEALERS[{"5TA": 0, "7TA": 5, "5NK": 7}[key]]
            rate = (LS_PRICE if machine is LS else OL_PRICE)[key]
            so = self.make({"doctype": "Sales Order", "customer": dealer, "company": self.company,
                            "transaction_date": str(day),
                            "delivery_date": str(due if isinstance(due, dt.date) else self.day(due)),
                            "items": [{"item_code": code, "qty": q, "rate": rate, "warehouse": self.main,
                                       "delivery_date": str(due if isinstance(due, dt.date) else self.day(due))}]})
            if kind == "so":
                pending[code].append((so, dealer, rate))
        elif kind in ("wo_done", "wo_open"):
            machine, key, q = x
            code = self._model(machine, key)
            bom = self.erp.list("BOM", filters=[["item", "=", code], ["is_default", "=", 1], ["docstatus", "=", 1]],
                                limit=1)
            wo = self.make({"doctype": "Work Order", "production_item": code, "bom_no": bom[0]["name"], "qty": q,
                            "company": self.company, "wip_warehouse": self.main, "fg_warehouse": self.main,
                            "source_warehouse": self.main, "use_multi_level_bom": 1, "skip_transfer": 1,
                            "planned_start_date": f"{day - dt.timedelta(days=3)} 08:00:00"})
            if kind == "wo_done":
                se = self.erp.call("erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry",
                                   work_order_id=wo["name"], purpose="Manufacture", qty=q)
                se = {k: v for k, v in se.items() if k not in ("name", "__islocal", "__unsaved", "docstatus")}
                se["items"] = [{k: v for k, v in r.items() if k not in ("name", "parent", "__islocal", "__unsaved")}
                               for r in se.get("items") or []]
                se.update(posting)
                self.make(se)
        elif kind == "deliver":
            machine, key = x
            code = self._model(machine, key)
            so, dealer, rate = pending[code].pop(0)
            self.make({"doctype": "Delivery Note", "customer": dealer, "company": self.company, **posting,
                       "items": [{"item_code": code, "qty": so["items"][0]["qty"], "rate": rate,
                                  "warehouse": self.main, "against_sales_order": so["name"],
                                  "so_detail": so["items"][0]["name"]}]})
        else:
            raise SewingError(f"unknown event {kind}")

    # ---- 4. the story in the hub
    def story(self) -> None:
        from wqops.hub.quality import change_control as CH  # noqa: PLC0415
        from wqops.hub.quality import complaints as C  # noqa: PLC0415
        from wqops.hub.quality import records as Q  # noqa: PLC0415

        conn = self.conn
        hook_code = HOOK
        # the supplier's material change, accepted on the strength of a certificate and one good lot
        a = CH.create(conn, BUYER, {
            "title": "旋梭供应商换料：梭尖材料 SUJ2 改为 GCr15SiMn", "kind": "supplier",
            "description": f"{HOOK_SUPPLIER}来函：旋梭 HSH-7.94A（{hook_code}）梭尖材料由 SUJ2 改为 GCr15SiMn，"
                           "热处理工艺相应调整，外形尺寸不变。",
            "reason": "供应商原材料来源调整", "owner": BUYER,
            "target_date": str(self.day(MATERIAL_CHANGE_DAY + 7)), "q_product": "yes", "q_regulatory": "no",
            "q_risk": "no", "q_validation": "no",
            "assessment": "供应商提供材质证明；首批换料来料按常规抽检（梭尖硬度 5 件），合格即接收。"})
        CH.submit(conn, BUYER, a["id"])
        CH.approve(conn, self.u(OPS), a["id"], SIGN)
        CH.update(conn, BUYER, a["id"], {"implementation": "自第 3 批起接收换料旋梭。"})
        CH.implement(conn, self.u(BUYER), a["id"])
        CH.update(conn, BUYER, a["id"], {"effectiveness": "换料后首批来料检验合格（梭尖硬度均在 58–62 HRC 内）。"})
        CH.close(conn, self.u(OWNER), a["id"], SIGN)
        # two dealers complain of broken thread
        m5ta, m7ta = self._model(LS, "5TA"), self._model(LS, "7TA")
        c1 = C.create(conn, SALES, {"received_on": str(self.day(74)), "customer": DEALERS[0],
                                   "description": f"{m5ta} 新机使用约两周后频繁断面线，高速时尤甚；更换旋梭后恢复正常。"
                                                  "客户共反映 3 台。",
                                   "item_code": m5ta, "quantity": 3, "injury": "no", "malfunction": "yes",
                                   "owner": QA, "source": "customer"}, today=self.today)
        C.start(conn, QA, c1["id"])
        C.update(conn, self.u(QA), c1["id"], {
            "investigation": "收回 3 只旋梭：梭尖有明显磨损和毛刺。3 台机器都在第 62 天以后生产，"
                             "用的是换料后的旋梭批次。"},
            today=self.today)
        c2 = C.create(conn, SALES, {"received_on": str(self.day(84)), "customer": DEALERS[5],
                                   "description": f"{m7ta} 厚料机缝牛仔布时断线，2 台。", "item_code": m7ta,
                                   "quantity": 2, "injury": "no", "malfunction": "yes", "owner": QA,
                                   "source": "customer"}, today=self.today)
        C.start(conn, QA, c2["id"])
        cp = C.open_capa(conn, QA, c1["id"])
        Q.update_capa(conn, cp["id"], QA, title="旋梭换料后断线（CMP 两起）", risk="high", owner=QA,
                      description=f"两家经销商反映断线：{c1['name']}（{m5ta}，3 台）、{c2['name']}（{m7ta}，2 台）。")
        Q.submit_capa(conn, cp["id"], QA)
        Q.update_capa(conn, cp["id"], QA,
                      containment="库存和在途的换料批次旋梭暂停使用、隔离；售后给客户免费更换旋梭。",
                      root_cause="旋梭换料后梭尖硬度偏低（来料检验 58.3–58.9 HRC，换料前约 60.6 HRC），"
                                 "虽在 58–62 HRC 规格内但接近下限；高速缝纫时梭尖磨损起毛刺，刮断面线。"
                                 "换料变更只看了材质证明和一批常规抽检，没有做耐磨验证。")
        self.out["story"] = {"supplier_change": a["name"], "complaints": [c1["name"], c2["name"]],
                             "capa": cp["name"]}

    def finished_change(self) -> None:
        """A design change already done: the needle plate A to B (a wider chamfer on the needle hole)."""
        from wqops.hub.plm import ecn as ECN  # noqa: PLC0415
        from wqops.hub.plm import parts as PT  # noqa: PLC0415
        from wqops.hub.quality import change_control as CH  # noqa: PLC0415

        conn, eng, eng2 = self.conn, self.u(ENG), self.u(ENG2)
        plate = PT.by_code(conn, NEEDLE_PLATE)
        ch = CH.create(conn, ENG, {"title": "针板针孔倒角加大（防勾线）", "kind": "product",
                                   "description": "针板针孔上沿倒角由 C0.2 改为 R0.5，抛光。",
                                   "reason": "装配检验发现薄料偶有勾线", "owner": ENG,
                                   "target_date": str(self.day(40)), "q_product": "yes", "q_regulatory": "no",
                                   "q_risk": "no", "q_validation": "yes",
                                   "assessment": "只改针孔倒角，不影响装配尺寸。",
                                   "validation_plan": "装 2 台，缝 0.3 mm 雪纺各 500 m，看有无勾线。"})
        ECN.add_item(conn, eng, ch["id"], {"part_id": plate["id"], "scope": "part"})
        ECN.set_effect(conn, eng, ch["id"], {"mode": "use_up"})
        ECN.analyse(conn, eng, ch["id"], self.erp)
        CH.submit(conn, ENG, ch["id"])
        CH.approve(conn, eng2, ch["id"], SIGN)
        PT.new_revision(conn, eng, plate["id"], ch["id"])
        PT.update(conn, eng, plate["id"], {"description": "针孔上沿倒角 R0.5，抛光（B 版）"})
        PT.release(conn, eng, plate["id"], SIGN)
        CH.update(conn, ENG, ch["id"], {"implementation": "针板 B 版发布；旧针板用完后切换。",
                                        "validation_result": "2 台缝制 0.3 mm 雪纺各 500 m，无勾线。"})
        CH.implement(conn, eng, ch["id"])
        CH.update(conn, ENG, ch["id"], {"effectiveness": "切换后两周装配检验未再发现勾线。"})
        CH.close(conn, self.u(OWNER), ch["id"], SIGN)
        self.out["finished_change"] = ch["name"]

    def inbox(self) -> None:
        """A FreeCAD batch waiting to be reviewed: the bobbin winder with a die-cast base."""
        from wqops.hub.plm import intake as IN  # noqa: PLC0415

        kids = self.kids["WQ88-2200"]
        nodes = [{"key": "Winder", "code": "WQ88-2200", "name": "绕线器部件"},
                 {"key": "Base", "code": "", "name": "绕线器座（铝压铸改型）", "material": "ADC12",
                  "volume_mm3": 18640.0}]
        links = [{"parent": "Winder", "child": "Base", "qty": 1}]
        for code, q in kids.items():
            if code == "WQ88-2201":
                continue
            nodes.append({"key": code, "code": code, "name": self.nodes[code]["name"]})
            links.append({"parent": "Winder", "child": code, "qty": format(q.normalize(), "f")})
        v = IN.receive(self.conn, source="freecad", sent_by="FreeCAD 设计电脑（演示）",
                       data={"nodes": nodes, "links": links}, file_name="绕线器-改型.FCStd")
        self.out["inbox"] = v["id"]

    def sync(self) -> None:
        """ERPNext into the hub and its objects (the quality modules read suppliers and items from there)."""
        from wqops.hub import sync as Y  # noqa: PLC0415
        from wqops.hub.ont import project as OP  # noqa: PLC0415

        Y.run(self.conn, self.erp, trigger="demo")
        OP.project(self.conn, manifest=self.m)

    def run(self) -> dict:
        from wqops.demo.quality import demo_signing  # noqa: PLC0415
        from wqops.hub import sync as Y  # noqa: PLC0415

        with demo_signing(self.m):
            self.masters()
            self.parts()
            self.suppliers()
            self.release()
            self.models()
            with Y.paused(self.conn):
                self.business()
            self.sync()
            self.story()
            self.finished_change()
            self.out["manual"] = SM.manual(self.conn, self.u(ENG), self._model(LS, MANUAL_MODEL), self.today)
            self.say(f"parts manual: {self.out['manual']['pages']} pages")
            self.inbox()
        return self.out


def load(conn, erp: ErpClient, manifest: dict, today: dt.date, say: Callable[[str], None] = print) -> dict:
    try:
        return Sewing(conn, erp, manifest, today, say).run()
    except ErpError as exc:
        raise SewingError(str(exc)) from exc
