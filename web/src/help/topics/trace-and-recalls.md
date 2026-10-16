---
title: Trace and recalls
group: Regulated modules
order: 6
summary: Where a lot came from and went, and recalling it.
needs: quality:view
---

**Trace** follows a lot either way. From a production lot: the incoming lots, suppliers, equipment and
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
