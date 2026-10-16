"""The company overview and the big screen (ADR-0018): the lights and their thresholds, weekly curves, receivables
by age, the chain, what waits for people, the panels each role sees, visitor mode hiding money and names, the
settings and the API. Fictional data only (the small business of tests/test_metrics.py, with invoices added)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from tests.test_metrics import AS_OF, DEMO, build
from wqops.erp import ErpClient
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import sync as Y
from wqops.hub.app import create_app
from wqops.hub.ont import overview as OV
from wqops.hub.ont import overview_rules as R
from wqops.hub.ont import project as OP

PW = "Demo pass 2026"
DANA, SAM, ALEX, LEE = "dana@demo.example", "sam@demo.example", "alex@demo.example", "lee@demo.example"


def erp():
    f = build()
    for i, (day, total) in enumerate([("2026-09-01", 100.0), ("2026-09-15", 300.0), ("2026-10-08", 250.0)], 1):
        f.put("Sales Order", f"SO-X{i}", customer="Bayside Hardware", customer_name="Bayside Hardware",
              transaction_date=day, grand_total=total, status="Completed", docstatus=1, items=[])
    f.put("Sales Invoice", "SINV-1", customer="Bayside Hardware", customer_name="Bayside Hardware",
          posting_date="2026-08-20", due_date="2026-09-19", grand_total=400.0, outstanding_amount=400.0, docstatus=1)
    f.put("Sales Invoice", "SINV-2", customer="Bayside Hardware", customer_name="Bayside Hardware",
          posting_date="2026-10-05", due_date="2026-11-04", grand_total=600.0, outstanding_amount=600.0, docstatus=1)
    f.put("Sales Invoice", "SINV-3", customer="Bayside Hardware", posting_date="2026-10-06", due_date="2026-11-05",
          grand_total=50.0, outstanding_amount=0, docstatus=1)
    f.put("Sales Invoice", "SINV-4", customer="Bayside Hardware", posting_date="2026-10-06", grand_total=999.0,
          outstanding_amount=999.0, docstatus=0)                                   # a draft does not count
    f.put("Purchase Invoice", "PINV-1", supplier="Gulf Fasteners", supplier_name="Gulf Fasteners",
          posting_date="2026-10-01", due_date="2026-10-31", grand_total=300.0, outstanding_amount=300.0, docstatus=1)
    return f


@pytest.fixture
def world(conn):
    Acc.sync(conn, DEMO)
    Y.run(conn, ErpClient("http://erp", transport=erp().transport()))
    OP.project(conn, manifest=DEMO)
    return conn


def u(conn, e):
    return Acc.get(conn, e)


def test_rules():
    rules = R.thresholds({"delivery": {"green": 90, "amber": 80}})
    assert rules["delivery"]["green"] == 90 and not rules["delivery"]["default"] and rules["sales"]["default"]
    assert [R.light(v, rules["delivery"]) for v in (95, 90, 85, 79.9, None)] == [
        "green", "green", "amber", "red", "unknown"]
    assert [R.light(v, rules["inventory"]) for v in (0, 3, 4)] == ["green", "amber", "red"]
    with pytest.raises(ValueError, match="better"):
        R.check_thresholds({"delivery": {"green": 70, "amber": 80}})
    with pytest.raises(ValueError, match="no panel"):
        R.check_thresholds({"weather": {"green": 1, "amber": 2}})
    with pytest.raises(ValueError, match="numbers"):
        R.check_thresholds({"finance": {"green": "10", "amber": 25}})
    d = dt.date(2026, 10, 12)
    weeks = R.by_week([(d, 10), (d - dt.timedelta(days=6), 5), (d - dt.timedelta(days=7), 1), (None, 9),
                       (d - dt.timedelta(days=40), 3)], d, 3)
    assert [(w["value"], w["count"]) for w in weeks] == [(0.0, 0), (1.0, 1), (15.0, 2)]
    assert R.vs_average([{"value": 10}, {"value": 30}, {"value": 30}]) == 150.0
    assert R.change([{"value": 10}, {"value": 15}]) == 50.0 and R.change([{"value": 0}, {"value": 5}]) is None
    ages = R.aging([(d, 1), (d - dt.timedelta(days=1), 2), (d - dt.timedelta(days=45), 3),
                    (d - dt.timedelta(days=100), 4), (None, 5)], d)
    assert [a["value"] for a in ages] == [6.0, 2.0, 3.0, 0.0, 4.0]
    p = {"light": {"value": 5, "unit": "%"}, "figures": [{"label": "x", "value": 9, "unit": "currency"},
                                                         {"label": "y", "value": 3, "unit": "%"}],
         "series": {"s": {"unit": "currency", "points": [{"week_ending": "a", "value": 50}, {"week_ending": "b",
                                                                                              "value": 100}]}},
         "lists": {"customers": [{"label": "Bayside"}]}}
    r = R.redact(p)
    assert r["figures"][0]["value"] is None and r["figures"][1]["value"] == 3 and r["lists"] == {}
    assert R.redact({**p, "lists": {"iso": [{"met": 1}], "late": [{"label": "x"}]}})["lists"] == {"iso": [{"met": 1}]}
    assert [x["value"] for x in r["series"]["s"]["points"]] == [50.0, 100.0] and r["light"]["value"] == 5


def test_overview_for_the_owner(world):
    out = OV.build(world, u(world, DANA), AS_OF, 8)
    panels = {p["key"]: p for p in out["panels"]}
    assert list(panels) == list(R.PANELS)
    fin = panels["finance"]
    figs = {f["label"]: f["value"] for f in fin["figures"]}
    # SINV-1 is 23 days past due; SINV-2 is not due; SINV-3 is paid; the draft does not count
    assert figs["Receivables"] == 1000.0 and figs["Overdue receivables"] == 400.0 and figs["Payables"] == 300.0
    assert fin["light"]["value"] == 40.0 and fin["light"]["color"] == "red"
    assert [a["value"] for a in fin["series"]["aging"]["points"]] == [600.0, 400.0, 0.0, 0.0, 0.0]
    assert fin["lists"]["late_customers"] == [{"label": "Bayside Hardware", "value": 400.0, "unit": "currency"}]
    sales = panels["sales"]
    assert sales["series"]["orders"]["points"][-1]["value"] == 250.0      # SO-X3 in the week ending 10-12
    assert panels["delivery"]["light"]["value"] == 50.0 and panels["delivery"]["light"]["color"] == "red"
    assert panels["production"]["light"]["color"] == "unknown"            # no lot released: unknown, not green
    keys = [s["key"] for s in out["chain"]]
    assert keys == ["po", "receipt", "iqc", "stock", "make", "release", "ship", "bill", "cash"]
    cash = next(s for s in out["chain"] if s["key"] == "cash")
    assert (cash["count"], cash["stuck"]) == (2, 1)


def test_what_each_role_sees(world):
    assert [p["key"] for p in OV.build(world, u(world, ALEX), AS_OF, 8)["panels"]] == ["sales", "delivery",
                                                                                       "inventory"]
    sam = OV.build(world, u(world, SAM), AS_OF, 8)
    assert "finance" not in [p["key"] for p in sam["panels"]]
    assert all(s["key"] not in ("bill", "cash") for s in sam["chain"])
    assert [w["kind"] for w in OV.waiting(world, u(world, LEE), AS_OF)] == []


def test_wall_and_settings(world):
    wall = OV.wall(world, u(world, DANA), AS_OF, 8, OV.settings(world))
    assert wall["visitor_mode"] is True and "waiting" not in wall
    fin = next(p for p in wall["panels"] if p["key"] == "finance")
    assert all(f["value"] is None for f in fin["figures"] if f["unit"] == "currency") and fin["lists"] == {}
    assert max(x["value"] for x in fin["series"]["billed"]["points"]) == 100.0     # the curve, not the amounts
    assert next(s for s in wall["chain"] if s["key"] == "stock")["count"] is None
    OV.set_setting(world, DANA, "visitor_mode", False)
    OV.set_setting(world, DANA, "thresholds", {"finance": {"green": 50, "amber": 60}})
    st = OV.settings(world)
    wall = OV.wall(world, u(world, DANA), AS_OF, 8, st)
    fin = next(p for p in wall["panels"] if p["key"] == "finance")
    assert fin["figures"][0]["value"] == 1000.0 and fin["light"]["color"] == "green"
    with pytest.raises(ValueError):
        OV.set_setting(world, DANA, "visitor_mode", "yes")
    with pytest.raises(KeyError):
        OV.set_setting(world, DANA, "colour", 1)


def test_overview_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url,
                              erp=ErpClient("http://erp", transport=erp().transport())))
    c.__enter__()
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        for e in (DANA, ALEX):
            Acc.set_password(conn, e, PW)
        Y.run(conn, ErpClient("http://erp", transport=erp().transport()))
        OP.project(conn, manifest=DEMO)

    def login(e):
        assert c.post("/api/login", json={"email": e, "password": PW}).status_code == 200

    login(ALEX)
    v = c.get("/api/overview").json()
    assert [p["key"] for p in v["panels"]] == ["sales", "delivery", "inventory"] and v["can_configure"] is False
    assert c.post("/api/overview/settings", json={"key": "visitor_mode", "value": False}).status_code == 403
    assert c.get("/api/overview?weeks=5").status_code == 400
    login(DANA)
    assert len(c.get("/api/overview?weeks=13").json()["panels"][0]["series"]["orders"]["points"]) == 13
    assert c.post("/api/overview/settings", json={"key": "thresholds", "value": {"x": 1}}).status_code == 409
    assert c.post("/api/overview/settings", content=b"{", headers={"content-type": "application/json"}
                  ).status_code == 400
    w = c.get("/api/overview/wall").json()
    assert w["visitor_mode"] is True and w["company"]
    c.__exit__(None, None, None)


def test_review_fixes(world):
    out = OV.build(world, u(world, DANA), AS_OF, 8, tz="America/New_York")
    panels = {p["key"]: p for p in out["panels"]}
    # less than 8 weeks of orders: the sales light waits; no CAPA, complaints or equipment yet: quality is unknown
    assert panels["sales"]["light"]["color"] == "unknown" and panels["quality"]["light"]["color"] == "unknown"
    figs = {f["label"]: f["value"] for f in panels["delivery"]["figures"]}
    assert figs["Delivered late, 30 days"] == 1
    with pytest.raises(ValueError, match="numbers"):
        R.check_thresholds({"finance": {"green": float("nan"), "amber": 25}})
    # only what differs from the starting point is kept as the company's own
    OV.set_setting(world, DANA, "thresholds", {"finance": {"green": 10, "amber": 25}, "delivery": {"green": 90,
                                                                                                "amber": 80}})
    OV.set_setting(world, DANA, "thresholds", {"sales": {"green": 95, "amber": 75}})
    assert OV.settings(world)["thresholds"] == {"delivery": {"green": 90, "amber": 80},
                                                "sales": {"green": 95, "amber": 75}}

