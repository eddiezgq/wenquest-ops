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
# the ready parts manual (rounds 124, 135): names in English; every lockstitch part in 3D, every BOM line placed
m = conn.execute("select m.edition, m.pages, m.names_open, p.item_code from plm_manuals m join plm_parts p on "
                 "p.id = m.part_id").fetchone()
models = conn.execute("select count(distinct p.id) as n from plm_files f join plm_part_revisions r on r.id = "
                      "f.revision_id join plm_parts p on p.id = r.part_id where f.kind = 'model' and p.item_code not "
                      "like 'WQ73-%%'").fetchone()["n"]
unplaced = conn.execute("select count(*) as n from plm_bom_lines l join plm_boms b on b.id = l.bom_id join plm_parts a "
                        "on a.id = b.part_id where a.item_code like 'WQ88-____' and jsonb_array_length(l.placements) "
                        "= 0").fetchone()["n"]
print(m["item_code"], "manual edition", m["edition"], len(m["pages"]), "pages;", models, "parts with 3D;", unplaced,
      "lines not placed")
assert m["item_code"] == "WQ88-0000-5TA" and m["edition"] == 1 and m["names_open"] == 0
assert models > 300 and unplaced == 0                  # round 135: every lockstitch part in 3D, every line placed
print("sewing demo: OK")
