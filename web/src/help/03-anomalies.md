# Anomalies and root causes

After every sync, rules look for problems:

- a sales order past its delivery date (critical after 7 days);
- a sales order due within 7 days with items short;
- an item short for open orders;
- a purchase order past its required-by date;
- a supplier below 90% on time (at least 3 receipt lines in 90 days);
- a rejected quality inspection;
- a corrective action step that is overdue.

Each anomaly has a suggested action and the role that usually handles it.

**Causes and impact.** Open an anomaly (or any order, item, purchase order, supplier or inspection) to see *why* —
for example *SO-0042 waits for bolts → bolts are short by 50 → the purchase order is 6 days late → the supplier
delivered 1 of 3 lines on time* — and *what it affects*, such as the orders and customers waiting for a rejected lot.
Every step states its reason and numbers.

**Life cycle.** Acknowledge, mark as being worked on, or close with a note. When the condition goes away for two
syncs in a row, the anomaly resolves itself. Everything is logged.
