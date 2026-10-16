---
title: Trace and recalls
group: Regulated modules
order: 6
summary: Where a lot came from and went, and recalling it.
video: trace-and-recalls
needs: quality:view
try:
  - id: drill
    text: 'Open *Trace and recalls*, set the list to *Closed* and open **Mock recall drill: KIT-M8**. Read the consignees, the shares notified and confirmed, and the effectiveness conclusion.'
    to: /quality/recalls
    expect: the status "closed", every consignee notified, and Dana's signature.
    tour:
      - target: '[data-help="recalls-list"]'
        text: Every recall with its class, status, owner and the day it opened. Choose Draft and open, Closed, Cancelled or All above the list.
      - target: '[data-help="recalls-trace"]'
        text: Opens the trace page. A recall starts from a trace.
  - id: trace-lot
    text: Choose *Trace a lot*. Start from *Production lot*, choose the released KIT-M8 lot and choose *Trace*.
    to: /quality/trace
    expect: the BOX-12 lot it used and its supplier, the deliveries found in ERPNext, and the recall it was on.
    tour:
      - target: '[data-help="trace-pick"]'
        text: Start from a production lot, an incoming lot or a complaint.
        elsewhere: Open the trace page first (Trace and recalls, then Trace a lot).
      - target: '[data-help="trace-back"]'
        text: Where the lot came from. The material lots, suppliers, equipment and nonconformances behind it, and other lots made from the same material lots.
        elsewhere: Trace a production lot first.
      - target: '[data-help="trace-delivered"]'
        text: Who received it, read from ERPNext delivery notes. A line with the same batch number is a match; a line with no batch number is listed as item only.
        elsewhere: Trace a production lot first.
  - id: trace-complaint
    text: Start from *Complaint* instead and choose the complaint about M8 bolts that strip.
    to: /quality/trace
    expect: a note that the complaint does not name both the item and the lot, so there is nothing to match.
  - id: start
    text: Sign in as **Jordan** (Quality). Trace the released KIT-M8 lot again and choose *Start a recall of these lots*.
    to: /quality/trace
    expect: a draft recall with "To open" and the deliveries that opening would take from ERPNext.
    tour:
      - target: '[data-help="trace-start-recall"]'
        text: Starts a draft recall of the lots in this trace.
        elsewhere: Trace a production lot first.
  - id: open
    demo: /quality/recalls/1
    text: Write the reason, choose a classification, set **Sam** as the owner, and write the strategy and the regulatory decision. Choose *Save*, then *Open the recall*.
    expect: '"Open: the consignee list is fixed." and the consignee list.'
    tour:
      - target: '[data-help="recall-what"]'
        text: The reason, the classification and the regulatory decision are people's decisions. WenQuest Ops does not make them.
        elsewhere: Open your draft recall first.
  - id: consignees
    demo: /quality/recalls/1
    text: For each consignee, enter the day notified and how, the day they confirmed, and choose *Save* on that row. Then write the effectiveness conclusion and choose *Save*.
    expect: the shares notified and confirmed go up; "To close" lists only what is still missing.
    tour:
      - target: '[data-help="recall-consignees"]'
        text: One row per delivery. Returned and corrected together are at most what was delivered. Download the list as a CSV here.
        elsewhere: Open the recall first.
  - id: close
    text: Sign out, sign in as **Dana** (Owner), open the recall and choose *Close (sign)* with your password.
    expect: the status "closed". Jordan, who raised and opened it, and Sam, who owns it, could not close it.
    tour:
      - target: '[data-help="recall-steps"]'
        text: Closed by someone who does not own it and did not raise or open it, once nothing is missing.
        elsewhere: Open the recall as Dana first.
blocks:
  - text: A recall does not open without the reason and a classification, and only its owner or Quality opens it.
    test: tests/test_recall.py::test_trace_and_recall
  - text: Once the recall is open, its consignee list is fixed and the lots in scope cannot change, not even in the database.
    test: tests/test_recall.py::test_trace_and_recall
  - text: A notice needs both the day and how, on a day between the opening and today; returned and corrected together are at most what was delivered.
    test: tests/test_recall.py::test_trace_and_recall
  - text: Whoever owns a recall, raised it or opened it cannot close it.
    test: tests/test_recall.py::test_trace_and_recall
  - text: A recall is not closed until every consignee is notified and the effectiveness conclusion, a note on those who did not confirm and the regulatory decision are written.
    test: tests/test_recall.py::test_trace_and_recall
  - text: A closed recall cannot be changed, and recalls are never deleted.
    test: tests/test_recall.py::test_trace_and_recall
questions:
  - q: What does "item only" mean on a delivery?
    a: The delivery note line has the item but no batch number, so it may hold the lot. Record batch numbers on delivery notes in ERPNext to narrow this.
  - q: Does tracing change anything?
    a: No. Tracing only reads; a recall starts only when you choose *Start a recall of these lots*.
  - q: What if the lot is delivered again after the recall opened?
    a: The consignee list stays fixed, and the recall page warns of deliveries of the lots made in ERPNext after it opened.
---

*Trace and recalls* in the sidebar lists the recalls. *Trace a lot* there, or *Trace* on a production record,
follows a lot either way. From a production lot: the incoming lots, suppliers, equipment and
nonconformance reports behind it, the other lots made from the same incoming lots, who received it and the complaints
about it. From an incoming lot: every production lot that used it, and onwards. From a complaint: the production lot
it names (same item and lot number; case and spaces do not matter). Who received a lot is read from ERPNext's delivery
notes: a line of the item with the same batch number is a match; a line of the item with no batch number may hold the
lot too, so it is listed as *item only* (record batch numbers on delivery notes in ERPNext to narrow this). Tracing
changes nothing.

A recall starts from a trace (*Start a recall of these lots*). In the draft, people write the reason, choose the
classification and write the strategy and the regulatory decision; WenQuest Ops shows which deliveries the recall
would take. Its owner or Quality opens it: the consignee list is taken from ERPNext and fixed. For each consignee,
record when and how they were notified (together), when they confirmed, and how much came back or was corrected (at
most what was delivered); the page counts the shares notified, confirmed and recovered, and warns of deliveries of
the lots made in ERPNext after the recall opened. Download the list as a CSV. Quality closes the recall with a
password, someone who does not own it and did not raise or open it, once every consignee is notified, with the
effectiveness conclusion, a note on anyone who did not confirm, and the regulatory decision. A draft is cancelled
with a reason; nothing is deleted.
