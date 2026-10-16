"""The fictional demo business (ADR-0012): the simulation's properties, and writing it with a stand-in ERPNext."""

import datetime as dt

import pytest

from tests.fake_erp import FakeErp
from wqops import company as C
from wqops.demo import load as LD
from wqops.demo import scenario as S
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import sync as Y
from wqops.hub.ont import anomaly as AN
from wqops.hub.ont import project as OP

TODAY = dt.date(2026, 10, 13)
DEMO = C.load(C.DEMO_FILE)


@pytest.fixture(scope="module")
def docs():
    return S.build(TODAY)


def test_repeatable_and_in_date_order(docs):
    assert [(d.day, d.kind, d.ref) for d in docs] == [(d.day, d.kind, d.ref) for d in S.build(TODAY)]
    assert [d.day for d in docs] == sorted(d.day for d in docs)
    assert docs[0].day == TODAY - dt.timedelta(days=89) and docs[-1].day <= TODAY
    n = S.summary(docs)
    assert 60 <= n["so"] <= 120 and 50 <= n["po"] <= 120 and n["opening"] == 1 and n["receipt_draft"] == 1
    assert all("(Demo)" in c for c in S.CUSTOMERS) and all("(Demo)" in s for s in S.SUPPLIERS)


def test_billing(docs):
    """ADR-0018: an invoice for each delivery and submitted receipt, payments only by today, a slow payer overdue."""
    n = S.summary(docs)
    assert n["sales_invoice"] == n["delivery"] and n["purchase_invoice"] == n["receipt"]
    assert 0 < n["payment_in"] < n["sales_invoice"] and 0 < n["payment_out"] < n["purchase_invoice"]
    by = {d.ref: d for d in docs}
    for d in docs:
        if d.kind in ("payment_in", "payment_out"):
            assert d.day < TODAY and by[d.data["invoice"]].day < d.day
    paid = {d.data["invoice"] for d in docs if d.kind == "payment_in"}
    late = [d for d in docs if d.kind == "sales_invoice" and d.ref not in paid and d.data["due"] < TODAY]
    assert late and any(d.data["customer"] == S.SLOW_PAYER for d in late)
    # the goods simulation is the same with or without the invoices
    goods = [d.ref for d in docs if d.kind not in S.BILLING]
    assert goods == [d.ref for d in S.build(TODAY) if d.kind not in S.BILLING]


def test_stock_never_negative_and_receipts_follow_orders(docs):
    stock: dict[str, float] = {}
    seen: set[str] = set()
    for d in docs:
        if d.kind == "opening":
            for ln in d.data["lines"]:
                stock[ln["item"]] = ln["qty"]
        elif d.kind == "po":
            seen.add(d.ref)
        elif d.kind in ("receipt", "receipt_draft"):
            assert d.data["po"] in seen
            if d.kind == "receipt":
                stock[d.data["item"]] += d.data["qty"]
        elif d.kind == "hold":
            stock[d.data["item"]] -= d.data["qty"]
        elif d.kind == "delivery":
            for ln in d.data["lines"]:
                stock[ln["item"]] -= ln["qty"]
                assert stock[ln["item"]] >= 0, (d.day, ln)


def test_typical_problems_are_built_in(docs):
    # a rejected bolt lot, moved to QC Hold the same day
    rej = [d for d in docs if d.kind == "inspection" and d.data["rejected"]]
    assert len(rej) == 1 and rej[0].data["item"] == S.KEY_ITEM
    assert any(d.kind == "hold" and d.day == rej[0].day for d in docs)
    assert all(v > rej[0].data["max"] for v in rej[0].data["values"])
    # other inspections are inside the limits, and the bolt diameter drifts upwards
    bolts = [d for d in docs if d.kind == "inspection" and d.data["item"] == S.KEY_ITEM and not d.data["rejected"]]
    assert len(bolts) >= 5
    assert all(d.data["min"] < v < d.data["max"] for d in bolts for v in d.data["values"])
    early = [sum(d.data["values"]) / 5 for d in bolts if (d.day - docs[0].day).days < S.DRIFT_FROM_DAY]
    late = [sum(d.data["values"]) / 5 for d in bolts if (d.day - docs[0].day).days >= S.DRIFT_FROM_DAY + 10]
    assert late and max(late) > max(early)
    # the last bolt order is past its date and not received; orders wait for bolts
    received = {d.data["po"] for d in docs if d.kind in ("receipt", "receipt_draft")}
    late_pos = [d for d in docs if d.kind == "po" and d.ref not in received and d.data["due"] < TODAY]
    assert any(d.data["item"] == S.KEY_ITEM for d in late_pos)
    shipped = {(d.data["so"], ln["line"]) for d in docs if d.kind == "delivery" for ln in d.data["lines"]}
    waiting = [d for d in docs if d.kind == "so" and d.data["due"] < TODAY and any(
        ln["item"] == S.KEY_ITEM and (d.ref, i) not in shipped for i, ln in enumerate(d.data["lines"]))]
    assert waiting
    # the supplier that is often late
    gulf = [d for d in docs if d.kind == "po" and d.data["supplier"] == S.GULF]
    arrived = {d.data["po"]: d.day for d in docs if d.kind == "receipt"}
    assert sum(1 for p in gulf if p.ref in arrived and arrived[p.ref] > p.data["due"]) >= 3
    # a cable receipt waits for inspection
    assert [d.data["item"] for d in docs if d.kind == "receipt_draft"] == ["CBL-12-50"]


def test_only_for_demo_companies():
    real = {**DEMO, "demo": False}
    with pytest.raises(LD.DemoError, match="demo: true"):
        LD.Loader(ErpClient("http://erp", transport=FakeErp().transport()), real, TODAY)


@pytest.fixture
def loaded(conn):
    fake = FakeErp()
    fake.put("Stock Settings", "Stock Settings")
    erp = ErpClient("http://erp", transport=fake.transport())
    for kind, name in (("Supplier Group", "Distributor"), ("Customer Group", "Commercial"),
                       ("Territory", "United States")):
        fake.put(kind, name, is_group=0)
    out = LD.Loader(erp, DEMO, TODAY, say=lambda _m: None).run()
    return conn, fake, erp, out


def test_writes_everything_in_order(loaded):
    _conn, fake, erp, out = loaded
    docs = S.build(TODAY)
    n = S.summary(docs)
    assert len(fake.docs["Sales Order"]) == n["so"] and len(fake.docs["Delivery Note"]) == n["delivery"]
    assert len(fake.docs["Purchase Receipt"]) == n["receipt"] + n["receipt_draft"]
    assert len(fake.docs["Item"]) == len(S.ITEMS) and len(fake.docs["Customer"]) == len(S.CUSTOMERS)
    assert {d["docstatus"] for d in fake.docs["Sales Order"].values()} == {1}
    drafts = [d for d in fake.docs["Purchase Receipt"].values() if d["docstatus"] == 0]
    assert [d["items"][0]["item_code"] for d in drafts] == ["CBL-12-50"]
    dn = next(iter(fake.docs["Delivery Note"].values()))
    so = fake.docs["Sales Order"][dn["items"][0]["against_sales_order"]]
    assert dn["items"][0]["so_detail"] in {r["name"] for r in so["items"]} and dn["set_posting_time"] == 1
    qi = fake.docs["Quality Inspection"][out["rejected_inspection"]]
    assert qi["reference_type"] == "Purchase Receipt" and len(qi["readings"]) == 1
    assert fake.docs["Item"]["CBL-12-50"]["inspection_required_before_purchase"] == 1
    assert fake.docs["Stock Settings"]["Stock Settings"]["action_if_quality_inspection_is_rejected"] == "Warn"
    si = next(iter(fake.docs["Sales Invoice"].values()))
    assert si["items"][0]["delivery_note"] in fake.docs["Delivery Note"] and si["docstatus"] == 1
    assert len(fake.docs["Payment Entry"]) == n["payment_in"] + n["payment_out"]
    pe = next(iter(fake.docs["Payment Entry"].values()))
    assert "__islocal" not in pe and pe["references"][0]["reference_name"] and pe["reference_no"].startswith("DEMO-")
    with pytest.raises(LD.DemoError, match="already loaded"):
        LD.Loader(erp, DEMO, TODAY).run()


def test_quality_history_for_the_rejected_lot(loaded):
    conn, fake, erp, out = loaded
    Acc.sync(conn, DEMO)
    fake.docs["Quality Inspection"][out["rejected_inspection"]]["status"] = "Rejected"   # ERPNext computes this
    Y.run(conn, erp)
    OP.project(conn, manifest=DEMO)
    names = LD.quality_records(conn, DEMO, out["rejected_inspection"], TODAY)
    assert names == ["NCR-00001", "CAPA-00001"]
    n = conn.execute("select * from ncr_records").fetchone()
    assert (n["severity"], n["status"], n["supplier"]) == ("major", "dispositioned", S.GULF)
    c = conn.execute("select * from capas").fetchone()
    assert c["status"] == "implementation" and c["owner"] == "pat@demo.example"
    OP.project(conn, manifest=DEMO)
    AN.detect(conn, TODAY)
    assert conn.execute("select 1 from anomalies where rule = 'capa_overdue'").fetchone()


@pytest.mark.parametrize("shift", range(21))
def test_every_problem_appears_whatever_the_date(shift):
    """The demo is built 'from today back 90 days', so every install day must show the same kinds of problems."""
    today = TODAY + dt.timedelta(days=shift)
    docs = S.build(today)
    assert [d.day for d in docs] == sorted(d.day for d in docs) and docs[-1].day <= today
    assert any(d.kind == "receipt_draft" and d.data["item"] == S.WAITING_ITEM for d in docs), "receipt waiting"
    assert sum(1 for d in docs if d.kind == "inspection" and d.data["rejected"]) == 1, "rejected lot"
    received = {d.data["po"] for d in docs if d.kind in ("receipt", "receipt_draft")}
    assert any(d.kind == "po" and d.ref not in received and d.data["due"] < today for d in docs), "late purchase order"
    shipped = {(d.data["so"], ln["line"]) for d in docs if d.kind == "delivery" for ln in d.data["lines"]}
    open_lines = [d for d in docs if d.kind == "so" and d.data["due"] < today
                  and any((d.ref, i) not in shipped for i in range(len(d.data["lines"])))]
    assert open_lines, "late sales order"
