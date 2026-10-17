"""Sample records for the regulated quality modules of the fictional demo company (ADR-0019 item 6).

    python -m wqops.demo.quality

The demo business (wqops/demo/load.py) brings orders, receipts, deliveries and one rejected lot. This adds what the
quality modules of ADR-0017 need so every page of the help center has something to open: approved suppliers, measuring
equipment, a sampling table and inspection plans with inspections in every state, two procedures in effect with their
reading, complaints, changes, a risk file, a production template with lots, a mock recall, a management review and a
few register entries. Each part leaves something done, something under way and something with a problem.

Everything is invented and made by plain code (no AI, no network). The sampling table rows are the demo company's own
numbers, not copied from a standard. Records are made by the demo people with the separation of duties the modules
enforce (whoever drafts does not approve). The people's passwords are not known to the installer, so while this runs
the demo signatures are accepted without one: only for a company manifest marked ``demo: true``. Every part runs on its
own and is skipped when the company already has such records (for example ones made while testing), so running it
again changes nothing.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import sys
from collections.abc import Callable, Iterator

from wqops.demo import scenario as S

DANA, SAM, PAT, JORDAN = (f"{n}@demo.example" for n in ("dana", "sam", "pat", "jordan"))
SIGN = "demo-installer"        # stands for the password while the demo history is written (see the module docstring)


class DemoQualityError(RuntimeError):
    pass


@contextlib.contextmanager
def demo_signing(manifest: dict) -> Iterator[None]:
    """Accept the demo people's signatures without their passwords, for the demo company only."""
    from wqops.hub.quality import records as Q  # noqa: PLC0415

    if not manifest.get("demo"):
        raise DemoQualityError("sample quality records are only loaded into a company manifest marked demo: true")
    real = Q.check_signer

    def check(conn, user: dict, password: str) -> None:
        if password != SIGN or not user.get("active", True):
            real(conn, user, password)

    Q.check_signer = check
    try:
        yield
    finally:
        Q.check_signer = real


def _u(conn, email: str) -> dict:
    from wqops.hub import accounts as Acc  # noqa: PLC0415

    u = Acc.get(conn, email)
    if u is None:
        raise DemoQualityError(f"{email} is not a person of the company yet")
    return u


def _exists(conn, sql: str, params=()) -> bool:
    return conn.execute(sql, params).fetchone() is not None


def _receipts(conn, item: str) -> list[str]:
    """Submitted receipts with a line of the item, newest first."""
    return [r["key"] for r in conn.execute(
        "select key from ont_objects where type = 'PurchaseReceipt' and coalesce((props->>'docstatus')::int, 1) = 1 "
        "and exists (select 1 from jsonb_array_elements(props->'lines') l where l->>'item_code' = %s) "
        "order by props->>'posting_date' desc, key desc", (item,))]


# ---------------------------------------------------------------- the parts

def suppliers(conn, today: dt.date) -> str:
    from wqops.hub.quality import asl as ASL  # noqa: PLC0415

    if _exists(conn, "select 1 from asl_entries"):
        return "skipped: the approved supplier list has entries"
    dana = _u(conn, DANA)
    due = today + dt.timedelta(days=365)
    for sup, risk, basis in ((S.COASTAL, "low", "Supplier questionnaire and 12 months of on-time lots"),
                             (S.BAYLINE, "medium", "ISO 9001 certificate on file, first-article lots accepted")):
        e = ASL.add(conn, JORDAN, sup, None, {"risk": risk, "basis": basis})
        ASL.approve(conn, dana, e["id"], SIGN, reason="Evaluated against QP-04", today=today,
                    review_due=str(due))
    e = ASL.add(conn, JORDAN, S.GULF, None, {"risk": "high", "basis": "Long-standing supplier; lot rejected this "
                                                                       "quarter (see the NCR)"})
    ASL.approve(conn, dana, e["id"], SIGN, reason="Kept on condition after the rejected bolt lot", today=today,
                review_due=str(today + dt.timedelta(days=90)),
                condition="100% thread check of the next 3 bolt lots and a supplier 8D")
    ASL.add(conn, JORDAN, S.SUMMIT, None, {"risk": "low", "basis": "Certificate of conformance requested"})
    return "3 suppliers approved (one on condition), 1 waiting for evaluation"


def equipment(conn, today: dt.date) -> str:
    from wqops.hub.quality import calibration as CAL  # noqa: PLC0415

    if _exists(conn, "select 1 from gauges"):
        return "skipped: measuring equipment is registered"
    dana = _u(conn, DANA)
    gauges = (("CAL-01", "Digital caliper 0-150 mm", 12, today - dt.timedelta(days=60)),
              ("CAL-02", "Outside micrometer 0-25 mm", 12, today - dt.timedelta(days=120)),
              ("TW-02", "Torque wrench 5-25 N·m", 6, today - dt.timedelta(days=230)))
    for code, name, months, done in gauges:
        g = CAL.add(conn, JORDAN, code, {"name": name, "interval_months": months, "location": "Receiving bench",
                                         "owner": JORDAN, "acceptance": "Within the maker's stated accuracy",
                                         "traceability": "Calibration lab certificate (demo)"})
        c = CAL.record(conn, JORDAN, g["id"], {"done_on": str(done), "done_by": "Bay Calibration Lab (Demo)",
                                               "result": "pass", "certificate": f"BCL-{code}-{done:%y%m}",
                                               "as_found": "In tolerance", "as_left": "In tolerance"}, today=today)
        CAL.approve(conn, dana, c["id"], SIGN, today=today)
    return "3 gauges in service, the torque wrench overdue"


def incoming(conn, today: dt.date) -> str:
    from wqops.hub.quality import iqc as I  # noqa: PLC0415

    if _exists(conn, "select 1 from iqc_inspections") or _exists(conn, "select 1 from iqc_plans"):
        return "skipped: inspection plans or inspections exist"
    dana, jordan = _u(conn, DANA), _u(conn, JORDAN)
    if not I.rows(conn, active_only=True):
        for lo, hi, n, ac in ((2, 50, 5, 0), (51, 500, 8, 0), (501, 5000, 13, 1)):
            r = I.add_row(conn, JORDAN, {"aql": 1.0, "level": "normal", "lot_min": lo, "lot_max": hi, "n": n,
                                         "ac": ac})
            I.verify_row(conn, DANA, r["id"], "Harbor Lane sampling table (demo values chosen by the company)")
    box = I.new_plan(conn, JORDAN, "BOX-12", 1.0, [
        {"name": "Board thickness", "kind": "measured", "lsl": 3.5, "usl": 4.5, "unit": "mm", "method": "Caliper"},
        {"name": "Print legible", "kind": "attribute"}], note="Corrugated box, 12 in")
    I.enable_plan(conn, dana, box["id"], SIGN)
    out = I.new_plan(conn, JORDAN, "OUTLET-DUP", 1.0, [{"name": "Housing undamaged", "kind": "attribute"},
                                                        {"name": "Terminal screws present", "kind": "attribute"}])
    I.enable_plan(conn, dana, out["id"], SIGN)
    cal = conn.execute("select id from gauges where code = 'CAL-01' and status = 'in_service'").fetchone()
    done = []
    for k, pr in enumerate(_receipts(conn, "BOX-12")[:3]):
        ins = I.start(conn, JORDAN, "BOX-12", receipt=pr, lot_no=f"CP-{pr[-4:]}", today=today)
        bad = k == 1                                           # the second newest lot is too thin
        vals = []
        for i in range(1, ins["n"] + 1):
            v = 3.3 if bad and i == 2 else round(3.9 + 0.05 * (i % 4), 2)
            vals += [{"sample": i, "characteristic": "Board thickness", "value": v},
                     {"sample": i, "characteristic": "Print legible", "passed": True}]
        I.enter(conn, JORDAN, ins["id"], vals)
        if cal:
            I.set_gauge(conn, JORDAN, ins["id"], "Board thickness", cal["id"], today=today)
        I.sign(conn, jordan, ins["id"], SIGN, today=today)
        if k < 2:                                              # the oldest waits for the decision
            I.decide(conn, dana, ins["id"], SIGN, "Rejected: board under the limit" if bad else "Released to stock",
                     today=today)
        done.append(ins["name"])
    rec = _receipts(conn, "OUTLET-DUP")
    if rec:
        ins = I.start(conn, SAM, "OUTLET-DUP", receipt=rec[0], lot_no="BE-2610", today=today)
        I.enter(conn, SAM, ins["id"], [{"sample": 1, "characteristic": "Housing undamaged", "passed": True},
                                       {"sample": 1, "characteristic": "Terminal screws present", "passed": True}])
        done.append(ins["name"])
    return f"2 plans in use; inspections {', '.join(done)} (released, rejected, waiting, under way)"


def documents(conn, today: dt.date) -> str:
    from wqops.hub.docs import control as CTL  # noqa: PLC0415
    from wqops.hub.docs import library as LIB  # noqa: PLC0415

    if _exists(conn, "select 1 from documents where status in ('effective', 'approved', 'in_review', 'draft')"):
        return "skipped: the library already has controlled documents"
    found = {}
    for key, like in (("qp05", "QP-05 Receiving%"), ("qp11", "QP-11 Calibration%")):
        row = conn.execute("select id from documents where original_name like %s and status = 'to_review' "
                           "order by id limit 1", (like,)).fetchone()
        if row is None:
            return "skipped: the demo documents are not imported (python -m wqops.demo.documents)"
        found[key] = row["id"]
    sam = _u(conn, SAM)
    fields = {"qp05": {"doc_type": "procedure", "process": "receiving", "number": "QP-05",
                       "title": "Receiving Inspection", "revision": "D", "effective_date": "2025-09-08"},
              "qp11": {"doc_type": "procedure", "process": "calibration", "number": "QP-11",
                       "title": "Calibration of Measuring Equipment", "revision": "A", "effective_date": "2024-08-19"}}
    for key, did in found.items():
        LIB.confirm(conn, JORDAN, did, fields[key])
        if key == "qp05":
            CTL.set_training(conn, JORDAN, did, {"roles": ["warehouse", "quality"], "people": []}, True, today=today)
        LIB.submit(conn, JORDAN, did)
        LIB.approve(conn, sam, did, SIGN, today)
    jordan = _u(conn, JORDAN)
    rec = conn.execute("select id from doc_training where document_id = %s and email = %s and status = 'pending'",
                       (found["qp05"], JORDAN)).fetchone()
    if rec:
        CTL.acknowledge(conn, jordan, rec["id"], SIGN)
    rv = CTL.record_review(conn, JORDAN, found["qp11"], "no_change", "Still matches how we calibrate", today=today)
    CTL.decide_review(conn, _u(conn, DANA), rv["id"], True, password=SIGN)
    return "QP-05 and QP-11 in effect; QP-05 reading confirmed by Jordan, pending for the warehouse; QP-11 reviewed"


def complaints(conn, today: dt.date) -> str:
    from wqops.hub.quality import complaints as C  # noqa: PLC0415

    if _exists(conn, "select 1 from complaints"):
        return "skipped: complaints exist"
    sam, jordan, dana = _u(conn, SAM), _u(conn, JORDAN), _u(conn, DANA)
    a = C.create(conn, SAM, {"received_on": str(today - dt.timedelta(days=20)), "customer": S.CUSTOMERS[0],
                             "description": "Two duplex outlets in a box of 10 had cracked housings.",
                             "item_code": "OUTLET-DUP", "quantity": 2, "injury": "no", "malfunction": "no",
                             "owner": SAM, "source": "customer"}, today=today)
    C.start(conn, SAM, a["id"])
    C.update(conn, sam, a["id"], {"investigation": "Housings cracked in transit: carton crushed on one corner. "
                                                   "Other lots checked, no cracks.",
                                  "root_cause": "Carton crushed in transit"}, today=today)
    C.assess(conn, jordan, a["id"], SIGN, answers={"q_harm": "no", "q_malfunction": "no", "q_recall": "no"},
             reportable=False, reason="Cosmetic damage in transit; no harm possible")
    C.update(conn, sam, a["id"], {"response": "Replaced two outlets; carrier claim filed."}, today=today)
    C.close(conn, dana, a["id"], SIGN)
    b = C.create(conn, SAM, {"received_on": str(today - dt.timedelta(days=4)), "customer": S.CUSTOMERS[1],
                             "description": "M8 bolts strip when tightened to the usual torque.",
                             "item_code": "HX-BOLT-M8", "quantity": 12, "injury": "no", "malfunction": "yes",
                             "owner": JORDAN, "source": "customer"}, today=today)
    C.start(conn, JORDAN, b["id"])
    C.update(conn, jordan, b["id"], {"investigation": "Checking whether the bolts came from the lot rejected at "
                                                      "receiving."}, today=today)
    C.create(conn, SAM, {"received_on": str(today), "customer": S.CUSTOMERS[2], "description":
                         "Label on a 4x6 roll printed off-centre.", "item_code": "LABEL-4X6", "injury": "unknown"},
             today=today)
    return "3 complaints: closed, under investigation, new"


def changes(conn, today: dt.date) -> str:
    from wqops.hub.quality import change_control as CH  # noqa: PLC0415

    if _exists(conn, "select 1 from changes"):
        return "skipped: changes exist"
    sam, pat, dana = _u(conn, SAM), _u(conn, PAT), _u(conn, DANA)
    a = CH.create(conn, JORDAN, {"title": "Second source for M8 bolts", "kind": "supplier",
                                 "description": "Qualify a second supplier for HX-BOLT-M8.",
                                 "reason": "One supplier, and a lot rejected this quarter", "owner": PAT,
                                 "target_date": str(today + dt.timedelta(days=30)), "q_product": "yes",
                                 "q_regulatory": "no", "q_risk": "yes", "q_validation": "no",
                                 "assessment": "Same drawing and grade; first lots get 100% thread check."})
    CH.submit(conn, JORDAN, a["id"])
    CH.approve(conn, sam, a["id"], SIGN)
    CH.update(conn, PAT, a["id"], {"implementation": "Second supplier added to the approved list on condition."})
    CH.implement(conn, pat, a["id"])
    CH.update(conn, PAT, a["id"], {"effectiveness": "Two lots received from both sources, no rejections."})
    CH.close(conn, dana, a["id"], SIGN)
    b = CH.create(conn, JORDAN, {"title": "Move QC Hold to the mezzanine cage", "kind": "process",
                                 "description": "Held lots go to a locked cage instead of the floor area.",
                                 "reason": "Held lots were picked by mistake once", "owner": SAM,
                                 "target_date": str(today + dt.timedelta(days=45)), "q_product": "no",
                                 "q_regulatory": "no", "q_risk": "yes", "q_validation": "no",
                                 "assessment": "Lowers the chance of shipping a held lot."})
    CH.submit(conn, JORDAN, b["id"])
    CH.create(conn, SAM, {"title": "New label printer for shipping", "kind": "equipment", "owner": SAM,
                          "description": "Replace the label printer at the shipping dock."})
    return "3 changes: closed, waiting for approval, draft"


def risk(conn, today: dt.date) -> str:
    from wqops.hub.quality import risk as RK  # noqa: PLC0415

    if _exists(conn, "select 1 from risk_files"):
        return "skipped: risk files exist"
    if not _exists(conn, "select 1 from risk_levels"):
        RK.load_example(conn, JORDAN)
    f = RK.create(conn, JORDAN, {"product": "M8 bolt kit (KIT-M8)", "scope": "Kitting and shipping of boxed M8 "
                                 "bolt kits", "owner": SAM})
    for it in ({"hazard": "Bolt from a rejected lot packed", "situation": "Held lot picked for kitting",
                "harm": "Joint fails at the customer", "severity": 4, "probability": 3,
                "controls": "Released lots only (production record checks the lot)",
                "verification": "Production record material check", "res_severity": 4, "res_probability": 1},
               {"hazard": "Wrong count in the box", "situation": "Count step skipped", "harm": "Short shipment",
                "severity": 2, "probability": 3, "controls": "Count check step with a weight check",
                "verification": "Production record step 1", "res_severity": 2, "res_probability": 1}):
        RK.add_item(conn, JORDAN, f["id"], it)
    RK.update(conn, JORDAN, f["id"], {"conclusion": "Residual risks acceptable with the controls in place.",
                                      "benefit_risk": "Kits reduce picking errors at the customer."})
    RK.approve(conn, _u(conn, DANA), f["id"], SIGN)
    g = RK.create(conn, JORDAN, {"product": "Packaging (BOX-12)", "scope": "Boxes used for shipping",
                                 "owner": SAM})
    RK.add_item(conn, JORDAN, g["id"], {"hazard": "Box too thin", "harm": "Goods damaged in transit",
                                        "severity": 2, "probability": 3})
    return "an approved risk file and a draft still missing controls"


def production(conn, today: dt.date) -> str:
    from wqops.hub.quality import production as PRD  # noqa: PLC0415

    if _exists(conn, "select 1 from prod_templates"):
        return "skipped: production templates exist"
    t = PRD.create_template(conn, JORDAN, {"code": "KIT-M8", "item_code": "HX-BOLT-M8",
                                           "title": "Boxed M8 bolt kit"})
    for st in ({"name": "Count 50 bolts", "kind": "check", "instruction": "Count by weight and by eye"},
               {"name": "Box weight", "kind": "measure", "instruction": "Weigh the closed box", "low": 0.9,
                "high": 1.1, "unit": "kg"},
               {"name": "Label number", "kind": "record", "instruction": "Write the label serial"}):
        PRD.add_step(conn, JORDAN, t["id"], st)
    PRD.update_template(conn, JORDAN, t["id"], {"materials": ["BOX-12"]})
    PRD.activate(conn, _u(conn, DANA), t["id"], SIGN)
    sam = _u(conn, SAM)       # recording needs quality:edit: the operations manager
    box = conn.execute("select id, lot_qty from iqc_inspections where item_code = 'BOX-12' and status = 'released' "
                       "order by id limit 1").fetchone()
    a = PRD.start(conn, SAM, {"template_id": t["id"], "lot_no": f"KIT-{today:%y%m}-01", "planned_qty": 20})
    PRD.record_step(conn, sam, a["id"], 1, SIGN, {"result": "pass"}, today=today)
    PRD.record_step(conn, sam, a["id"], 2, SIGN, {"value": 1.02}, today=today)
    PRD.record_step(conn, sam, a["id"], 3, SIGN, {"text": "L-004512"}, today=today)
    if box:
        PRD.add_material(conn, SAM, a["id"], box["id"], min(20, box["lot_qty"]))
    PRD.set_quantities(conn, SAM, a["id"], {"good_qty": 20, "scrap_qty": 0})
    PRD.submit(conn, SAM, a["id"])
    PRD.decide(conn, _u(conn, DANA), a["id"], SIGN, True, "Released")
    b = PRD.start(conn, SAM, {"template_id": t["id"], "lot_no": f"KIT-{today:%y%m}-02", "planned_qty": 20})
    PRD.record_step(conn, sam, b["id"], 1, SIGN, {"result": "pass"}, today=today)
    return "template KIT-M8 in use; one lot released, one in production"


def recall(conn, today: dt.date) -> str:
    from wqops.hub.quality import recall as RC  # noqa: PLC0415

    if _exists(conn, "select 1 from recalls"):
        return "skipped: recalls exist"
    lot = conn.execute("select id from prod_records where status = 'released' order by id limit 1").fetchone()
    if lot is None:
        return "skipped: no released lot to practise on"
    r = RC.create(conn, JORDAN, {"title": "Mock recall drill: KIT-M8", "reason": "Yearly recall exercise",
                                 "owner": SAM, "classification": "not yet classified", "scope": [lot["id"]],
                                 "strategy": "Trace the lot, list the customers, time how long it takes"})
    sam = _u(conn, SAM)
    RC.open_recall(conn, sam, r["id"], today=today)
    for c in RC.consignees(conn, r["id"]):
        RC.record_contact(conn, SAM, c["id"], {"notified_on": str(today), "method": "phone (drill)",
                                               "confirmed_on": str(today), "note": "Drill: no product returned"},
                          today=today)
    RC.update(conn, sam, r["id"], {"effectiveness": "Lot traced in 25 minutes; every customer reached.",
                                   "regulatory_decision": "Drill only: nothing to report"})
    RC.close(conn, _u(conn, DANA), r["id"], SIGN, today=today)
    return "a closed mock recall"


def review(conn, today: dt.date, tz: str) -> str:
    from wqops.hub.quality import review as MR  # noqa: PLC0415

    if _exists(conn, "select 1 from mgmt_reviews"):
        return "skipped: management reviews exist"
    r = MR.create(conn, JORDAN, {"title": "Q3 management review", "period_start": str(today - dt.timedelta(
        days=89)), "period_end": str(today), "chair": DANA, "meeting_on": str(today),
        "attendees": "Dana Owner, Sam Ops, Jordan Quality, Pat Buyer"})
    MR.collect(conn, JORDAN, r["id"], today=today, tz=tz)
    MR.update(conn, JORDAN, r["id"], {"notes": {
        "incoming": "Bolt and box lots rejected: Gulf kept on condition.",
        "complaints": "One closed, one under investigation (bolts stripping).",
        "equipment": "Torque wrench overdue for calibration: book it."},
        "conclusion": "The quality system is suitable, adequate and effective; supplier control needs work."})
    MR.add_action(conn, JORDAN, r["id"], {"text": "Calibrate torque wrench TW-02", "owner": JORDAN,
                                          "due": str(today + dt.timedelta(days=14))}, today=today)
    MR.add_action(conn, JORDAN, r["id"], {"text": "Supplier audit at Gulf Fasteners", "owner": PAT,
                                          "due": str(today + dt.timedelta(days=60))}, today=today)
    MR.sign(conn, _u(conn, DANA), r["id"], SIGN, today=today)
    return "a signed management review with 2 open actions"


def registers(conn, today: dt.date) -> str:
    from wqops.hub.system import registers as RG  # noqa: PLC0415

    if _exists(conn, "select 1 from qms_register_entries"):
        return "skipped: the registers have entries"
    for person, topic in (("Lee Warehouse", "QP-05 Receiving Inspection"), ("Pat Buyer", "QP-04 Purchasing")):
        RG.create(conn, JORDAN, "training", {"person": person, "topic": topic,
                                             "trained_on": str(today - dt.timedelta(days=30)),
                                             "result": "competent", "trainer": "Jordan Quality"})
    a = RG.create(conn, JORDAN, "audits", {"audit_date": str(today - dt.timedelta(days=40)), "area": "Receiving",
                                           "auditor": "Sam Ops", "findings": "Sampling table row not checked",
                                           "nonconformities": 1, "followed_up": "yes"})
    RG.sign(conn, _u(conn, DANA), a["id"], SIGN)
    RG.create(conn, JORDAN, "objectives", {"objective": "Supplier on-time delivery", "target": "95%",
                                           "actual": "88%", "status": "off track",
                                           "reviewed_on": str(today - dt.timedelta(days=10))})
    return "training, an internal audit and an objective"


def digital(conn, today: dt.date) -> str:
    """ADR-0020 (20b-20d): a device identifier, a measurement file in an inspection under way and a machine's
    readings waiting for a person. The GTIN uses GS1 prefix 952, which GS1 keeps for examples."""
    from wqops.hub import integration as IG  # noqa: PLC0415
    from wqops.hub import udi as UD  # noqa: PLC0415
    from wqops.hub.quality import iqc as I  # noqa: PLC0415
    from wqops.hub.quality import measurements as ME  # noqa: PLC0415

    if _exists(conn, "select 1 from udi_items") or _exists(conn, "select 1 from integration_tokens"):
        return "skipped: device identifiers or machine tokens exist"
    UD.set_di(conn, JORDAN, "HX-BOLT-M8", {"agency": "gs1", "gtin": "9521234567899"})
    cal = conn.execute("select id from gauges where code = 'CAL-01' and status = 'in_service'").fetchone()
    if I.enabled_plan(conn, "BOX-12") is None or cal is None:
        return "device identifier for HX-BOLT-M8; no BOX-12 plan or caliper for the measurement examples"
    ins = I.start(conn, JORDAN, "BOX-12", 200, supplier="Coastal Packaging (Demo)", lot_no="CP-DEMO-7", today=today)
    raw = b"Sample,Board thickness,Flap width\n1,4.02,60.1\n2,3.97,60.0\n3,4.05,59.8\n4,3.99,60.2\n"
    seen = ME.preview(conn, ins["id"], "box12-cmm-export.csv", raw, gauge_id=cal["id"])["print"]
    ME.import_file(conn, _u(conn, JORDAN), ins["id"], "box12-cmm-export.csv", raw, SIGN, seen=seen,
                   gauge_id=cal["id"], today=today)
    row, token = IG.new_token(conn, DANA, "Receiving gauge station (Demo)", ["measurements:send"])
    IG.receive_measurements(conn, IG.authenticate(conn, token), {
        "inspection": ins["name"], "equipment": "CAL-01",
        "readings": [{"sample": 5, "characteristic": "Board thickness", "value": 4.01},
                     {"sample": 6, "characteristic": "Board thickness", "value": 3.96}]})
    return (f"HX-BOLT-M8 identified (GTIN 09521234567899); {ins['name']} with a measurement file on samples 1-4 and "
            f"2 readings from {row['name']} waiting")


PARTS: list[tuple[str, Callable]] = [
    ("Approved suppliers", suppliers), ("Measuring equipment", equipment), ("Incoming inspection", incoming),
    ("Documents", documents), ("Complaints", complaints), ("Changes", changes), ("Risk", risk),
    ("Production", production), ("Recall", recall), ("Registers", registers), ("Management review", review),
    ("Digital factory", digital),
]


def load(conn, manifest: dict, today: dt.date) -> dict[str, str]:
    """Every part in its own transaction: one that fails or is skipped leaves the others."""
    tz = (manifest.get("company") or {}).get("timezone") or "UTC"
    out: dict[str, str] = {}
    with demo_signing(manifest):
        for label, fn in PARTS:
            try:
                with conn.transaction():
                    out[label] = fn(conn, today, tz) if fn is review else fn(conn, today)
            except Exception as exc:  # reported; the other parts go on
                out[label] = f"not loaded: {exc}".splitlines()[0]
    return out


def main() -> int:
    """Add the sample quality records to a demo installation (also run by wqops.demo.load)."""
    from wqops import company as C  # noqa: PLC0415
    from wqops.hub import accounts as Acc  # noqa: PLC0415
    from wqops.hub import db as DB  # noqa: PLC0415
    from wqops.hub.ont import api as OA  # noqa: PLC0415
    from wqops.hub.ont import project as OP  # noqa: PLC0415

    manifest = C.load(os.environ["WQO_COMPANY_FILE"])
    if not manifest.get("demo"):
        print("sample quality records are only loaded into a company manifest marked demo: true", file=sys.stderr)
        return 1
    with DB.connect(os.environ["WQO_DB"]) as conn:
        DB.migrate(conn)
        Acc.sync(conn, manifest)
        out = load(conn, manifest, OA.today(manifest))
        OP.project(conn, manifest=manifest)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
