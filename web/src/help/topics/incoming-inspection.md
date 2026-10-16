---
title: Incoming inspection
group: Quality
order: 3
summary: Sampling table, inspection plans, inspecting a lot and deciding.
needs: quality:view
try:
  - id: open
    text: Sign in as **Jordan** (Quality). Open *Incoming inspection* in the sidebar.
    to: /quality/iqc
    expect: under *Lots waiting*, the CBL-12-50 receipt with "no plan"; under *Inspections*, a BOX-12 lot "signed, to decide" and an OUTLET-DUP lot "in progress".
    tour:
      - target: '[data-help="iqc-tabs"]'
        text: Inspections, plans, the company's sampling table and the inspection levels.
      - target: '[data-help="iqc-waiting"]'
        text: Receipt lines of items to inspect on receipt. Items with a plan in use can be sampled here.
      - target: '[data-help="iqc-inspections"]'
        text: The inspections, with the level and n, Ac and Re they were sampled with.
  - id: table
    text: Choose the *Sampling table* tab.
    to: /quality/iqc?tab=table
    expect: three rows for AQL 1 at normal inspection, each checked against the demo company's own table.
    tour:
      - target: '[data-help="iqc-table"]'
        text: The company's own rows. WenQuest Ops does not supply these numbers. A row an inspection used cannot change.
        elsewhere: Choose the Sampling table tab first.
  - id: plan
    text: Choose the *Plans* tab and open the **BOX-12** plan.
    to: /quality/iqc?tab=plans
    expect: the status "enabled", a fingerprint, and two characteristics, board thickness (3.5 to 4.5 mm) and print legible.
    tour:
      - target: '[data-help="iqc-plans"]'
        text: Every plan and version. A plan in use is frozen; a change is a new version.
        elsewhere: Choose the Plans tab first.
  - id: decide-own
    demo: /quality/iqc/3
    text: Go back to *Inspections* and open the BOX-12 lot that is *signed, to decide*. You signed it. Enter your password and choose *Release (sign)*.
    expect: '"someone other than the inspector who signed releases or rejects the lot". The lot stays undecided.'
    tour:
      - target: '[data-help="iqc-summary"]'
        text: The lot, the plan version and the sampling used. The result was judged by code from the readings.
        elsewhere: Open the BOX-12 lot that is signed, to decide (Incoming inspection, Inspections).
      - target: '[data-help="iqc-decide"]'
        text: Someone other than the inspector releases or rejects the lot here.
  - id: release
    text: Sign out and sign in as **Dana** (Owner). Open the same inspection, write a note, enter your password and choose *Release (sign)*.
    expect: the status "released" and a link to an ERPNext draft waiting on the Drafts page.
  - id: finish
    demo: /quality/iqc/4
    text: Sign in as **Jordan** again and open the OUTLET-DUP lot *in progress*. Choose **pass** for every reading, choose *Save the readings*, then enter your password and choose *Sign (judge the lot)*.
    expect: the status "signed, to decide" with the result "accept".
    tour:
      - target: '[data-help="iqc-readings"]'
        text: One row per sample unit, one column per characteristic. A unit fails if any of its readings fails.
        elsewhere: Open the OUTLET-DUP inspection first.
  - id: levels
    text: Choose the *Inspection levels* tab and read the lots decided for each supplier and item, and the switching rules.
    to: /quality/iqc?tab=levels
    expect: each lot shown as A (accepted) or R (rejected), and the default switching rules.
    tour:
      - target: '[data-help="iqc-levels"]'
        text: The level each supplier's item is inspected at. The rules suggest a switch; a person switches, with a reason.
        elsewhere: Choose the Inspection levels tab first.
      - target: '[data-help="iqc-rules"]'
        text: The starting rules are defaults. Set them to what your procedure says.
  - id: erpnext-draft
    text: Open *Quality* and choose the *Incoming inspection* tab. Enter a sample size of **5** for the CBL-12-50 receipt and choose *Draft inspection*.
    to: /quality?tab=incoming
    expect: the Drafts page with the ERPNext quality inspection waiting for Quality to confirm.
    tour:
      - target: '[data-help="incoming-receipts"]'
        text: Receipts of items marked for inspection in ERPNext that have no inspection yet.
        elsewhere: Choose the Incoming inspection tab on the Quality page first.
blocks:
  - text: A plan is enabled by someone other than the person who drafted it, with a password, and only when the sampling table has rows for its AQL. Once enabled it cannot change.
    test: tests/test_iqc.py::test_plans_frozen_once_enabled
  - text: Sampling table rows that overlap are refused, and marking a row as checked needs the source it was compared with.
    test: tests/test_iqc.py::test_sampling_table_is_company_data
  - text: A lot cannot be inspected without a plan in use, and a lot on a receipt keeps the receipt's supplier and quantity.
    test: tests/test_iqc.py::test_inspection_from_receipt_to_erpnext
  - text: An inspection is signed only when every reading is entered; after signing the readings cannot change and the inspection cannot be voided.
    test: tests/test_iqc.py::test_inspection_from_receipt_to_erpnext
  - text: The inspector does not release or reject their own lot. A lot sampled with a row not yet checked is released only with a reason.
    test: tests/test_iqc.py::test_inspection_from_receipt_to_erpnext
  - text: A switch of inspection level needs a reason, and reduced cannot go straight to tightened.
    test: tests/test_iqc.py::test_switching_is_suggested_and_confirmed
questions:
  - q: Where do the sample size, Ac and Re come from?
    a: From the company's sampling table, for the plan's AQL, the lot size and the supplier's inspection level. WenQuest Ops does not supply these numbers.
  - q: What happens to a rejected lot?
    a: The result goes to Drafts as a rejected ERPNext quality inspection to confirm, and a nonconformance report is opened. Once the inspection is submitted in ERPNext the report is linked to it.
  - q: Why can I not start an inspection for a lot?
    a: The item has no plan in use, the lot is already being inspected, or the supplier is not approved for the item on *Approved suppliers*. The message says which.
---

Items marked *inspection required before purchase* in ERPNext are listed on *Quality*, tab *Incoming inspection*,
when received. Draft an inspection there with your sample size; Quality confirms it on the Drafts page; enter the
readings in ERPNext.

To inspect by plan and sampling table instead, use **Incoming inspection** in the sidebar:

- **Sampling table**: the owner or Quality enters the rows of the company's sampling table (AQL, inspection level,
  lot size range, sample size n and acceptance number Ac; Re is Ac + 1) from the company's own controlled copy of the
  standard it uses. WenQuest Ops does not supply these numbers. Mark a row as checked, naming the source, once someone
  has compared it with that copy. A row an inspection used cannot change: archive it and add a new one.
- **Plans**: a plan for an item gives its AQL and the characteristics to check: measured ones with a lower and/or upper
  limit, or pass/fail ones. A plan is enabled with a password by someone other than the person who drafted it, and is
  then frozen; a change is a new version.
- **Inspections**: start one from a waiting receipt line (or for a lot not on a receipt). The sampling table gives n,
  Ac and Re for the lot size and the supplier's inspection level; a lot smaller than the sample is inspected piece by
  piece. Enter the readings and sign: the lot is judged by code (a sample unit fails if any reading fails; the lot is
  accepted with Ac or fewer failing units). Someone other than the inspector then releases or rejects the lot with a
  password. The result goes to Drafts as an ERPNext quality inspection to confirm; a rejected lot gets a
  nonconformance report, which is linked to that inspection once it is submitted in ERPNext. A lot sampled with a row
  not yet checked is flagged, and releasing it needs a reason.
- **Inspection levels**: the switching rules suggest moving a supplier's item between normal, tightened and reduced
  inspection from the lots decided at its current level. A person switches, with a reason. The starting rules are
  defaults: set them to what your procedure says. Who may do what (the "someone other" rules) can be switched off
  there too.
