"""After the demo load and one more sync, the hub's copy of ERPNext must match ERPNext (ADR-0006). Runs inside the
hub container:

    docker compose exec -T hub python - < .github/scripts/erp_consistency.py

Compares every submitted sales order, purchase order and delivery note (modified time and the fields the dashboard
uses) and prints the history of any document that differs, then fails.
"""

import os
import sys
import time

from wqops.erp_setup import client_from_env
from wqops.hub import db as DB
from wqops.hub import sync as Y

CHECK = {"Sales Order": ["per_delivered", "status"], "Purchase Order": ["per_received", "status"],
         "Delivery Note": ["status"], "Purchase Receipt": ["status"]}

erp = client_from_env()
conn = DB.connect(os.environ["WQO_DB"])
for _ in range(40):
    try:
        print("sync", Y.run(conn, erp, trigger="manual"))
        break
    except Y.SyncBusy:
        time.sleep(3)
else:
    sys.exit("the sync stayed busy")

bad = 0
for doctype, fields in CHECK.items():
    theirs = {r["name"]: r for r in erp.list(doctype, filters=[["docstatus", "=", 1]],
                                             fields=["name", "modified", *fields], limit=0)}
    ours = {r["name"]: r for r in conn.execute(
        "select name, modified, data from erp_docs where doctype = %s and docstatus = 1 and not deleted", (doctype,))}
    print(doctype, len(theirs), "in ERPNext,", len(ours), "in the hub")
    for name in sorted(set(theirs) | set(ours)):
        t, o = theirs.get(name), ours.get(name)
        same = t and o and str(t["modified"]) == o["modified"] and all(t.get(f) == o["data"].get(f) for f in fields)
        if same:
            continue
        bad += 1
        print(f"DIFF {doctype} {name}: ERPNext {t and {k: t[k] for k in ['modified', *fields]}}; "
              f"hub {o and {'modified': o['modified'], **{f: o['data'].get(f) for f in fields}}}")
        for e in conn.execute("select e.kind, e.modified, e.run_id, e.recorded_at, e.data->>%s as v "
                              "from erp_events e where doctype = %s and name = %s order by id",
                              (fields[0], doctype, name)):
            print("   event", dict(e))
if bad:
    print("cursors", [dict(r) for r in conn.execute("select * from erp_sync_state order by doctype")])
    print("runs", [dict(r) for r in conn.execute("select id, trigger, status, counts, started_at, finished_at "
                                                 "from erp_sync_runs order by id")])
    sys.exit(f"{bad} documents differ between ERPNext and the hub")
print("the hub matches ERPNext")

