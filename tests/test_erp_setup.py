"""Creating the business in ERPNext from the company manifest (Phase 1 item 3). No network: a fake ERPNext."""

from __future__ import annotations

import ast
import datetime as dt
import json

import httpx
import pytest

from wqops import company as C
from wqops import erp_setup as S
from wqops.erp import ErpClient, ErpError


class FakeErp:
    """Just enough of the ERPNext REST API: resources by name, list with equality filters, insert."""

    def __init__(self, company="Harbor Lane Supply (Demo)"):
        self.docs = {"Company": {company: {"name": company}}}
        self.inserted = []
        self.seen_headers = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen_headers.append(dict(request.headers))
        parts = request.url.path.split("/")
        if request.url.path == "/api/method/ping":
            return httpx.Response(200, json={"message": "pong"})
        doctype = parts[3]
        store = self.docs.setdefault(doctype, {})
        if request.method == "GET" and len(parts) == 5:
            name = parts[4]
            return httpx.Response(200, json={"data": store[name]}) if name in store else httpx.Response(404, json={})
        if request.method == "GET":
            flt = json.loads(request.url.params["filters"])
            rows = [d for d in store.values() if all(d.get(f[1]) == f[3] for f in flt)]
            return httpx.Response(200, json={"data": [{"name": d["name"]} for d in rows]})
        doc = json.loads(request.content)
        if doctype == "Warehouse":
            doc["name"] = f"{doc['warehouse_name']} - HLS"
        elif doctype == "Department":
            doc["name"] = f"{doc['department_name']} - HLS"
        elif doctype == "Social Login Key":
            doc["name"] = "wenquest_ops"
        else:
            doc["name"] = f"{doc['address_title']}-{doc['address_type']}"
        if request.method == "PUT":
            store[parts[4]].update(doc)
            return httpx.Response(200, json={"data": store[parts[4]]})
        store[doc["name"]] = doc
        self.inserted.append(doc)
        return httpx.Response(200, json={"data": doc})

    def client(self):
        return ErpClient("http://erp", "key", "secret", site="frontend", transport=httpx.MockTransport(self.handler))


@pytest.mark.parametrize(("start", "today", "expect"), [
    ("01-01", dt.date(2026, 10, 12), (dt.date(2026, 1, 1), dt.date(2026, 12, 31))),
    ("07-01", dt.date(2026, 10, 12), (dt.date(2026, 7, 1), dt.date(2027, 6, 30))),
    ("07-01", dt.date(2026, 3, 1), (dt.date(2025, 7, 1), dt.date(2026, 6, 30))),
    ("10-01", dt.date(2026, 10, 1), (dt.date(2026, 10, 1), dt.date(2027, 9, 30))),
])
def test_fiscal_year(start, today, expect):
    assert S.fiscal_year(start, today) == expect


def test_wizard_args_follow_the_manifest():
    m = C.load(C.DEMO_FILE)
    system, setup = S.wizard_args(m, dt.date(2026, 10, 12))
    assert system["system_settings_data"] == {"language": "en", "country": "United States", "currency": "USD",
                                              "time_zone": "America/New_York", "date_format": "mm-dd-yyyy"}
    a = setup["args"]
    assert a["company_name"] == "Harbor Lane Supply (Demo)" and a["company_abbr"] == "HLS"
    assert (a["fy_start_date"], a["fy_end_date"]) == ("2026-01-01", "2026-12-31")
    assert a["chart_of_accounts"] == "Standard" and a["setup_demo"] == 0 and a["enable_telemetry"] == 0


def test_apply_creates_once_and_is_idempotent():
    m = C.load(C.DEMO_FILE)
    erp = FakeErp()
    lines = S.apply(m, erp.client())
    assert sum("created" in x for x in lines) == 4 + 4 + 2          # warehouses, departments, addresses
    wh = {d["name"]: d for d in erp.inserted if d["doctype"] == "Warehouse"}
    assert set(wh) == {"Receiving Dock - HLS", "Main Stock - HLS", "QC Hold - HLS", "Shipping Dock - HLS"}
    assert all(d["parent_warehouse"] == "All Warehouses - HLS" for d in wh.values())
    addr = [d for d in erp.inserted if d["doctype"] == "Address"]
    assert {a["address_type"] for a in addr} == {"Office", "Warehouse"}
    assert all(a["links"] == [{"link_doctype": "Company", "link_name": "Harbor Lane Supply (Demo)"}] for a in addr)
    n = len(erp.inserted)
    again = S.apply(m, erp.client())
    assert len(erp.inserted) == n and all("exists" in x for x in again)
    h = erp.seen_headers[0]
    assert h["authorization"] == "token key:secret" and h["host"] == "frontend"


def test_apply_needs_the_company_and_reports_erp_errors():
    m = C.load(C.DEMO_FILE)
    with pytest.raises(ErpError, match="setup wizard"):
        S.apply(m, FakeErp(company="Someone Else").client())

    def broken(request):
        if request.method == "POST":
            return httpx.Response(417, json={"exception": "frappe.exceptions.ValidationError: bad warehouse"})
        return FakeErp().handler(request)

    c = ErpClient("http://erp", transport=httpx.MockTransport(broken))
    with pytest.raises(ErpError, match=r"417.*bad warehouse"):
        S.apply(m, c)


def test_transit_warehouse_type():
    m = C.load(C.DEMO_FILE)
    m["warehouses"] = [{"id": "truck", "name": "In Transit", "site": "dc-tampa", "kind": "transit"}]
    m["departments"], m["sites"] = [], [{"id": "dc-tampa", "name": "DC", "kind": "warehouse"}]
    erp = FakeErp()
    lines = S.apply(m, erp.client())
    assert erp.inserted[0]["warehouse_type"] == "Transit" and lines[-1] == "address DC: none given"


def test_cli(tmp_path, capsys):
    assert S.main(["wizard-args", str(C.DEMO_FILE)]) == 0
    first, second = capsys.readouterr().out.strip().splitlines()
    assert ast.literal_eval(first)["system_settings_data"]["currency"] == "USD"
    assert ast.literal_eval(second)["args"]["company_abbr"] == "HLS"
    bad = tmp_path / "c.yaml"
    bad.write_text("version: 1\n", encoding="utf-8")
    assert S.main(["apply", str(bad)]) == 1
    assert S.main(["nope"]) == 2


def test_apply_sets_up_erpnext_sign_in(monkeypatch):
    monkeypatch.setenv("WQO_PUBLIC_URL", "https://ops.example.com")
    monkeypatch.setenv("WQO_ERP_SSO_SECRET", "s3cret")
    m = C.load(C.DEMO_FILE)
    erp = FakeErp()
    assert "ERPNext sign-in through WenQuest Ops: created" in S.apply(m, erp.client())
    key = erp.docs["Social Login Key"]["wenquest_ops"]
    assert key["client_secret"] == "s3cret" and key["base_url"] == "https://ops.example.com"
    assert "ERPNext sign-in through WenQuest Ops: updated" in S.apply(m, erp.client())
