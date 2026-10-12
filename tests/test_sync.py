"""ERPNext sync (ADR-0006) against the in-memory ERPNext stand-in; documents are fictional."""

import httpx
import pytest

from tests.fake_erp import FakeErp
from wqops.erp import ErpClient
from wqops.hub import db as DB
from wqops.hub import sync as Y


@pytest.fixture
def fake():
    f = FakeErp()
    f.put("Warehouse", "Main Stock - HLS")
    f.put("Item", "WIDGET-01", item_name="Widget", stock_uom="Nos")
    f.put("Customer", "Bayside Hardware")
    f.put("Supplier", "Gulf Fasteners")
    f.put("Purchase Order", "PUR-ORD-00001", supplier="Gulf Fasteners",
          items=[{"item_code": "WIDGET-01", "qty": 100, "warehouse": "Main Stock - HLS"}])
    f.put("Stock Ledger Entry", "SLE-0001", item_code="WIDGET-01", actual_qty=100, docstatus=1)
    return f


@pytest.fixture
def erp(fake):
    return ErpClient("http://erp", "k", "s", transport=fake.transport())


def events(conn, **where):
    sql = "select doctype, name, kind from erp_events"
    if where:
        sql += " where " + " and ".join(f"{k} = %({k})s" for k in where)
    return [(r["doctype"], r["name"], r["kind"]) for r in conn.execute(sql + " order by id", where).fetchall()]


def test_first_run_records_every_document(conn, erp):
    out = Y.run(conn, erp)
    assert out["events"]["Item"] == 1 and out["events"]["Purchase Order"] == 1 and out["events"]["deleted"] == 0
    assert set(events(conn)) == {("Warehouse", "Main Stock - HLS", "created"), ("Item", "WIDGET-01", "created"),
                                 ("Customer", "Bayside Hardware", "created"), ("Supplier", "Gulf Fasteners", "created"),
                                 ("Purchase Order", "PUR-ORD-00001", "created"),
                                 ("Stock Ledger Entry", "SLE-0001", "created")}
    po = conn.execute("select data from erp_events where doctype = 'Purchase Order'").fetchone()["data"]
    assert po["items"][0]["qty"] == 100  # orders are fetched whole, with their rows
    s = Y.status(conn)
    assert s["events"] == 6 and s["last_run"]["status"] == "ok"
    assert {d["doctype"]: d["documents"] for d in s["doctypes"]}["Item"] == 1


def test_second_run_only_pulls_changes(conn, erp, fake):
    Y.run(conn, erp)
    fake.requests.clear()
    assert sum(Y.run(conn, erp)["events"].values()) == 0
    assert all(r.url.path.count("/") == 3 for r in fake.requests)  # only list calls, no documents fetched again
    fake.put("Item", "WIDGET-01", item_name="Widget, blue")
    fake.put("Purchase Order", "PUR-ORD-00001", docstatus=1)
    Y.run(conn, erp)
    fake.put("Purchase Order", "PUR-ORD-00001", docstatus=2)
    Y.run(conn, erp)
    assert events(conn, doctype="Item") == [("Item", "WIDGET-01", "created"), ("Item", "WIDGET-01", "updated")]
    assert [e[2] for e in events(conn, doctype="Purchase Order")] == ["created", "submitted", "cancelled"]
    doc = conn.execute("select data, docstatus from erp_docs where name = 'WIDGET-01'").fetchone()
    assert doc["data"]["item_name"] == "Widget, blue" and doc["docstatus"] == 0


def test_same_modified_time_across_pages(conn, erp, fake):
    """250 items changed in the same instant, pages of 100: none skipped, none twice."""
    for i in range(250):
        fake.put("Item", f"BULK-{i:03d}", modified="2026-10-12 08:00:00.000000")
    Y.run(conn, erp, page=100, specs=(Y.Spec("Item"),))
    names = [e[1] for e in events(conn, doctype="Item")]
    assert len(names) == 251 and len(set(names)) == 251


def test_interrupted_run_resumes(conn, erp, fake):
    for i in range(30):
        fake.put("Customer", f"Customer {i:02d}")
    fake.fail_after = 6
    with pytest.raises(httpx.ConnectError):
        Y.run(conn, erp, page=10)
    run = conn.execute("select status, error from erp_sync_runs").fetchone()
    assert run["status"] == "error" and "ConnectError" in run["error"]
    done = len(events(conn, doctype="Customer"))
    assert 0 < done < 31
    fake.fail_after = None
    Y.run(conn, erp, page=10)
    names = [e[1] for e in events(conn, doctype="Customer")]
    assert len(names) == 31 and len(set(names)) == 31


def test_deleted_documents(conn, erp, fake):
    Y.run(conn, erp)
    fake.delete("Customer", "Bayside Hardware")
    fake.delete("Item", "WIDGET-01")
    fake.put("Item", "WIDGET-01", item_name="Widget, new")  # same code used again after the deletion
    out = Y.run(conn, erp)
    assert out["events"]["deleted"] == 1
    assert events(conn, doctype="Customer")[-1] == ("Customer", "Bayside Hardware", "deleted")
    assert conn.execute("select deleted from erp_docs where name = 'Bayside Hardware'").fetchone()["deleted"]
    item = conn.execute("select deleted, data from erp_docs where name = 'WIDGET-01'").fetchone()
    assert not item["deleted"] and item["data"]["item_name"] == "Widget, new"
    # a later run does not mark it again
    assert Y.run(conn, erp)["events"]["deleted"] == 0


def test_document_gone_between_list_and_fetch(conn, fake):
    class Vanishing(ErpClient):
        def get(self, doctype, name):
            return None if name == "PUR-ORD-00001" else super().get(doctype, name)

    Y.run(conn, Vanishing("http://erp", transport=fake.transport()))
    assert events(conn, doctype="Purchase Order") == []
    assert Y._cursor(conn, "Purchase Order")[1] == "PUR-ORD-00001"


def test_one_run_at_a_time(conn, erp, db_url):
    other = DB.connect(db_url)
    try:
        other.execute("select pg_advisory_lock(%s)", (Y.LOCK_ID,))
        with pytest.raises(Y.SyncBusy):
            Y.run(conn, erp)
    finally:
        other.close()
    assert Y.run(conn, erp)["events"]["Item"] == 1


def test_fetch_page_asks_erpnext_to_compare(fake, erp):
    """Ordering and comparisons are left to ERPNext, so its collation decides, not Python's."""
    Y.fetch_page(erp, "Item", ("2026-10-12 09:00:01.000000", "WIDGET-01"), 5, fields=["name", "modified"])
    first, second = (dict(r.url.params) for r in fake.requests)
    assert first["filters"] == '[["modified", "=", "2026-10-12 09:00:01.000000"], ["name", ">", "WIDGET-01"]]'
    assert first["order_by"] == "name asc"
    assert second["filters"] == '[["modified", ">", "2026-10-12 09:00:01.000000"]]'
    assert second["order_by"] == "modified asc, name asc"


def test_recording_transport(tmp_path, fake):
    erp = ErpClient("http://erp", "key", "secret", transport=Y.RecordingTransport(tmp_path, fake.transport()))
    assert erp.list("Item", fields=["*"])[0]["name"] == "WIDGET-01"
    rec = (tmp_path / "0001.json").read_text(encoding="utf-8")
    assert '"path": "/api/resource/Item"' in rec and "secret" not in rec


def test_cli(conn, db_url, fake, monkeypatch, capsys):
    import wqops.erp_setup as E

    monkeypatch.setenv("WQO_DB", db_url)
    monkeypatch.setattr(E, "client_from_env",
                        lambda transport=None: ErpClient("http://erp", transport=fake.transport()))
    assert Y.main(["run"]) == 0
    assert '"Item": 1' in capsys.readouterr().out
    assert Y.main(["status"]) == 0
    assert '"events": 6' in capsys.readouterr().out


def _hub(db_url, fake, **kw):
    from fastapi.testclient import TestClient

    from wqops import company as C
    from wqops.hub import accounts as Acc
    from wqops.hub.app import create_app

    app = create_app({}, lambda: (C.load(C.DEMO_FILE), "ok"), db_url=db_url,
                     erp=ErpClient("http://erp", transport=fake.transport()), **kw)
    c = TestClient(app)
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.set_password(conn, "dana@demo.example", "Owner pass 2026")
        Acc.set_password(conn, "lee@demo.example", "Warehouse pass 1")
    return c


def test_sync_api_and_permissions(db_url, fake):
    c = _hub(db_url, fake)
    assert c.get("/api/sync/status").status_code == 401
    c.post("/api/login", json={"email": "lee@demo.example", "password": "Warehouse pass 1"})
    assert c.get("/api/sync/status").json()["events"] == 0
    assert c.post("/api/sync/run").status_code == 403           # running a sync needs settings:edit
    c.post("/api/login", json={"email": "dana@demo.example", "password": "Owner pass 2026"})
    r = c.post("/api/sync/run")
    assert r.status_code == 200 and r.json()["events"]["Customer"] == 1
    s = c.get("/api/sync/status").json()
    assert s["events"] == 6 and s["last_run"]["trigger"] == "person:dana@demo.example"
    fake.fail_after = len(fake.requests)
    r = c.post("/api/sync/run")
    assert r.status_code == 502 and "ERPNext" in r.json()["detail"]
    assert c.get("/api/sync/status").json()["last_run"]["status"] == "error"
    c.__exit__(None, None, None)


def test_background_sync(db_url, fake):
    import time

    c = _hub(db_url, fake, sync_seconds=0.2)
    with DB.connect(db_url) as conn:
        for _ in range(50):
            if conn.execute("select count(*) as n from erp_sync_runs where status = 'ok'").fetchone()["n"] >= 2:
                break
            time.sleep(0.1)
        runs = conn.execute("select trigger, status from erp_sync_runs order by id").fetchall()
    c.__exit__(None, None, None)
    assert len(runs) >= 2 and {r["trigger"] for r in runs} == {"schedule"}
    assert len(Y.status(DB.connect(db_url))["doctypes"]) == len(Y.SPECS)
