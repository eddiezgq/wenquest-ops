"""CI, the sewing machine demo company (ADR-0026 26f), inside the hub container after the demo load: the story's
numbers come out of the impact analysis of a design change to the rotary hook, from what ERPNext holds."""
import os

from wqops.erp_setup import client_from_env
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub.plm import ecn as ECN
from wqops.hub.plm import parts as PT
from wqops.hub.quality import change_control as CH

conn = DB.connect(os.environ["WQO_DB"])
eng = Acc.get(conn, "caiming@demo.example")
class Undo(Exception):
    pass


try:
    with conn.transaction():          # looked at, then undone: the demo stays as loaded
        ch = CH.create(conn, eng["email"], {"title": "CI", "kind": "product", "owner": eng["email"],
                                            "description": "CI", "reason": "CI"})
        ECN.add_item(conn, eng, ch["id"], {"part_id": PT.by_code(conn, "WQ88-1711")["id"], "scope": "part"})
        row = ECN.analyse(conn, eng, ch["id"], client_from_env())["impact"]["data"]["parts"][0]
        print({k: row[k] for k in ("stock", "purchase_orders", "work_orders", "sales_orders")})
        tops = sorted(a["code"] for a in row["used_in"] if a["top"])
        print(tops)
        assert row["stock"] == "120", row["stock"]
        assert [p["open"] for p in row["purchase_orders"]] == ["60", "60"], row["purchase_orders"]
        assert len(row["work_orders"]) == 2 and len(row["sales_orders"]) == 3, row
        assert tops == ["WQ88-0000", "WQ88-0000-5NK", "WQ88-0000-5TA", "WQ88-0000-5TK", "WQ88-0000-7TA"], tops
        assert not any(t.startswith("WQ73") for t in tops)         # the overlock machine has no rotary hook
        raise Undo
except Undo:
    pass
n = conn.execute("select count(*) as n from plm_parts where status = 'released'").fetchone()["n"]
capa = conn.execute("select status, root_cause from capas").fetchone()
print(n, "parts released;", capa["status"])
assert n >= 500 and capa["status"] == "investigation" and "梭尖硬度" in capa["root_cause"]
# the ready parts manual (round 124, 27d): every page has a picture, 6 of them from the 3D models, names in English
m = conn.execute("select m.edition, m.pages, m.names_open, p.item_code from plm_manuals m join plm_parts p on "
                 "p.id = m.part_id").fetchone()
kinds = [r["kind"] for r in conn.execute("select e.kind from plm_explodes e")]
print(m["item_code"], "manual edition", m["edition"], len(m["pages"]), "pages;", kinds.count("model"), "from 3D")
assert m["item_code"] == "WQ88-0000-5TA" and m["edition"] == 1 and m["names_open"] == 0
assert all(p["picture"] for p in m["pages"]) and kinds.count("model") == 6
print("sewing demo: OK")
