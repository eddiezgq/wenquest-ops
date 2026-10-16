---
title: Anomalies and root causes
group: Daily work
order: 2
summary: Problems the rules find, with their causes and what they affect.
try:
  - id: list
    text: Sign in as **Sam** (Operations manager) and open *Anomalies*.
    to: /anomalies
    expect: active problems, among them HX-BOLT-M8 short for open orders, late sales orders and purchase orders from Gulf Fasteners (Demo).
    tour:
      - target: '[data-help="anomalies-list"]'
        text: Each problem with its severity, the rule that found it, the record it is about and since when.
  - id: open-short
    text: Open the anomaly that says **HX-BOLT-M8** is short.
    expect: what is short and by how much, and a suggested action usually handled by purchasing.
    tour:
      - target: '[data-help="anomaly-hint"]'
        text: What to do about it, and the role that usually does it.
        elsewhere: Open the HX-BOLT-M8 anomaly first.
  - id: causes
    text: Read *Causes and impact* on the same page.
    expect: the purchase orders that should bring more bolts and how late they are, and the orders and customers waiting.
    tour:
      - target: '[data-help="anomaly-causes"]'
        text: Why it happened, step by step, and what it affects. Every step states its reason and numbers.
        elsewhere: Open an anomaly first.
  - id: acknowledge
    text: Type a note, for example **Chasing Gulf**, and choose *Acknowledge*.
    expect: the status "ack" and a new line in the log with your email and the note.
    tour:
      - target: '[data-help="anomaly-status"]'
        text: Acknowledge, mark it as being worked on, or close it. A note is optional.
        elsewhere: Open an anomaly first.
      - target: '[data-help="anomaly-log"]'
        text: Everything that happened to this anomaly, and who did it.
  - id: close
    text: Type a note and choose *Close*.
    expect: the status "closed"; the buttons are gone.
  - id: closed-list
    text: Go back to *Anomalies* and choose *Closed* in the list at the top right.
    to: /anomalies
    expect: the anomaly you closed.
    tour:
      - target: '[data-help="anomalies-show"]'
        text: Active, resolved, closed or all.
  - id: sales-view
    text: Sign in as **Alex** (Sales) and open *Anomalies*. Open a late sales order.
    to: /anomalies
    expect: only order and item problems. The causes stop at the item; purchase orders and suppliers are not shown.
blocks:
  - text: A closed anomaly cannot be opened again. If the problem is still there, a new anomaly is opened.
    test: tests/test_anomalies.py::test_life_cycle
  - text: An anomaly is not resolved after one good sync; the problem must be gone twice in a row.
    test: tests/test_anomalies.py::test_life_cycle
  - text: You see only the anomalies your role may see. Sales cannot open a purchase order anomaly.
    test: tests/test_anomalies.py::test_anomaly_api_by_role
  - text: Causes and impact leave out the records your role may not see.
    test: tests/test_anomalies.py::test_anomaly_api_by_role
questions:
  - q: I closed an anomaly and it came back. Why?
    a: The problem was still there at the next check, so the rules opened a new anomaly. Closing does not fix the cause.
  - q: When does a problem become critical?
    a: A sales order more than 7 days past its delivery date becomes critical. The log shows it as escalated.
  - q: Can the rules be changed?
    a: The thresholds, such as the 90% supplier on-time target, are kept in the rule file of the system, not on a page.
---

After every sync, rules look for problems:

- a sales order past its delivery date (critical after 7 days);
- a sales order due within 7 days with items short;
- an item short for open orders;
- a purchase order past its required-by date;
- a supplier below 90% on time (at least 3 receipt lines in 90 days);
- a rejected quality inspection;
- a corrective action step that is overdue.

Each anomaly has a suggested action and the role that usually handles it.

**Causes and impact.** Open an anomaly (or any order, item, purchase order, supplier or inspection) to see *why*,
for example *SO-0042 waits for bolts → bolts are short by 50 → the purchase order is 6 days late → the supplier
delivered 1 of 3 lines on time*, and *what it affects*, such as the orders and customers waiting for a rejected lot.
Every step states its reason and numbers.

**Life cycle.** *Acknowledge*, mark it *Working on it*, or *Close* it, each with an optional note. When the condition goes away for two
syncs in a row, the anomaly resolves itself. Everything is logged.

![A late order traced to a short item and a late supplier](img/anomaly-late-order.webp)
