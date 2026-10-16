---
title: Approved suppliers
group: Quality
order: 4
summary: Who you may buy what from, on what basis, until when.
needs: quality:view
---

**Approved suppliers** in the sidebar lists which supplier may deliver which item: one entry per supplier and item,
or per supplier for all its items (an entry for the item counts first). Quality or the owner enters a supplier as a
draft with its risk, what the approval rests on (certificates, audit, sample inspection) and when to re-evaluate it;
someone else approves it with a password. With conditions written in, the approval is *conditional*. An approved
entry changes only by a signed re-evaluation (with a later re-evaluation date), or after it is suspended. Suspending,
disqualifying and qualifying again (back to a draft) need a reason. Nothing is deleted.

Incoming inspection reads the list: a lot from a supplier with no approved entry for the item cannot be inspected (a
supplier suspended or disqualified for all items is blocked for every item); a
conditional supplier or an overdue re-evaluation is flagged on the inspection. Purchase order drafts list any item
the supplier is not approved for. The list also shows each entry's inspected lots, rejection rate and open
nonconformances. If the ISO 9001 supplier approval register was used, *Bring in from the register* makes a draft
entry for each supplier ERPNext knows, with the register's basis and next review, for someone else to approve (a
removed supplier comes in disqualified); from then on the ISO supplier check reads the list, item by item. The list is
in use once it has an entry: before that, incoming inspection does not consult it. Both rules (the list is enforced;
approval by someone other than whoever entered or last changed the entry) can be switched off at the bottom of the
page.
