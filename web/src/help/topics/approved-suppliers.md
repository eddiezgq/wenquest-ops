---
title: Approved suppliers
group: Quality
order: 4
summary: Who you may buy what from, on what basis, until when.
video: approved-suppliers
needs: quality:view
try:
  - id: open
    text: Sign in as **Jordan** (Quality). Open *Approved suppliers* in the sidebar.
    to: /quality/suppliers
    expect: Coastal Packaging (Demo) and Bayline Electrical (Demo) approved, Gulf Fasteners (Demo) conditional, and Summit Tools (Demo) still a draft.
    tour:
      - target: '[data-help="asl-list"]'
        text: One entry per supplier and item, or per supplier for all its items, with its status, risk, re-evaluation date and how its lots went.
  - id: conditional
    text: Choose *Open* on the **Gulf Fasteners (Demo)** row and read its basis and conditions.
    expect: conditions that ask for a full thread check of the next 3 bolt lots and a supplier 8D, approved by Dana, with its history and signature.
    tour:
      - target: '[data-help="asl-entry"]'
        text: What the approval rests on, the conditions, who approved it, and the history and signatures of the entry.
        elsewhere: Choose Open on a row first.
  - id: approve-own
    text: Open the **Summit Tools (Demo)** draft, which you entered. Write a reason, pick a re-evaluation date next year, enter your password and choose *Approve (sign)*.
    expect: '"someone other than the person who entered or changed the supplier''s entry approves it". It stays a draft.'
  - id: approve
    text: Sign out and sign in as **Dana** (Owner). Open the Summit Tools (Demo) draft, write a reason (for example **Certificate of conformance received**), pick a re-evaluation date next year, enter your password and choose *Approve (sign)*.
    expect: '"Approved." and the status "approved".'
  - id: suspend
    text: Open Summit Tools (Demo) again, write a reason (for example **Late certificates**) and choose *Suspend*.
    expect: '"Suspended." Lots from Summit Tools (Demo) can no longer be inspected until it is approved again.'
  - id: settings
    demo: /quality/suppliers
    text: Read the two settings at the bottom of the page. Leave them as they are.
    expect: the list is enforced at incoming inspection, and approval is by someone other than whoever entered or last changed the entry.
    tour:
      - target: '[data-help="asl-settings"]'
        text: The company can switch either rule off. Only the owner and Quality can change them.
blocks:
  - text: A lot from a supplier with no approved entry for the item, or whose entry is a draft or suspended, cannot be inspected.
    test: tests/test_asl.py::test_incoming_inspection_reads_the_list
  - text: Whoever entered or last changed an entry does not approve it. An approval needs a reason, what it rests on and a re-evaluation date after today, signed with a password.
    test: tests/test_asl.py::test_approvals_signed_and_kept
  - text: An approved entry changes only by a signed re-evaluation or after it is suspended, not even in the database.
    test: tests/test_asl.py::test_approvals_signed_and_kept
  - text: A disqualified supplier is qualified again, back to a draft, before it can be approved.
    test: tests/test_asl.py::test_approvals_signed_and_kept
  - text: Entries are never deleted.
    test: tests/test_asl.py::test_approvals_signed_and_kept
questions:
  - q: A supplier has an entry for all items and one for a single item. Which counts?
    a: The entry for the item counts first.
  - q: When is an approval conditional?
    a: When conditions are written in at approval or re-evaluation. Inspections of that supplier's lots then show the conditions.
  - q: The list is empty. Is incoming inspection blocked?
    a: No. The list is in use once it has an entry; before that, incoming inspection does not consult it.
  - q: We kept suppliers in the ISO 9001 supplier approval register. Do we enter them again?
    a: No. *Bring in from the register* makes a draft entry for each supplier ERPNext knows, for someone else to approve.
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
