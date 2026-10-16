---
title: Drafts
group: Daily work
order: 4
summary: Nothing is written to ERPNext or sent until a person confirms.
video: drafts
try:
  - id: open
    text: Sign in as **Pat** (Purchasing) and open *Drafts*.
    to: /drafts
    expect: the drafts waiting for you, or "None.".
    tour:
      - target: '[data-help="drafts-show"]'
        text: Waiting for you, confirmed, rejected, failed or all.
  - id: make-po
    text: Open the item **HX-BOLT-M8** and choose *Draft a replenishment purchase order*.
    to: /o/Item/HX-BOLT-M8
    expect: the *Drafts* page with a new purchase order marked "AI draft", from Gulf Fasteners (Demo), for what is short.
    tour:
      - target: '[data-help="object-draft"]'
        text: Prepares a draft from the records. Nothing is sent to ERPNext yet.
  - id: read
    text: Read the draft.
    to: /drafts
    expect: the summary with how much is short and for which orders, the supplier, the required-by date and the lines.
    tour:
      - target: '[data-help="drafts-item"]'
        text: What was prepared, by whom, and from which records.
  - id: sales-cannot-see
    text: Sign in as **Alex** (Sales) and open *Drafts*.
    to: /drafts
    expect: the purchase order is not listed. Sales does not draft purchase orders.
  - id: delay-message
    text: Open *Anomalies*, open a late sales order, then the order itself, and choose *Draft a delay message to the customer*.
    to: /anomalies
    expect: a customer message draft with the customer, a subject "Update on your order" and the order number, and a text with no supplier names.
  - id: confirm-message
    text: Choose *Confirm* on the message.
    to: /drafts
    expect: the status "confirmed" and a *Copy to send* button. Nothing is sent; you send it yourself.
    tour:
      - target: '[data-help="drafts-decide"]'
        text: Confirm, or write a reason and reject. Next to the buttons it says what confirming does.
  - id: reject-po
    text: Sign in as **Pat** again. On the purchase order, type the reason **Test only** and choose *Reject*.
    to: /drafts
    expect: the draft leaves the list. Choose *Rejected* at the top right to see it with its reason.
blocks:
  - text: Nothing is written to ERPNext before someone confirms; a confirmed purchase order is created in ERPNext as a draft, not submitted.
    test: tests/test_drafts.py::test_propose_confirm_creates_an_erpnext_draft
  - text: A draft cannot be confirmed twice.
    test: tests/test_drafts.py::test_propose_confirm_creates_an_erpnext_draft
  - text: Only a role allowed to make that kind of draft can confirm it. Sales cannot draft purchase orders; purchasing cannot confirm a quality inspection.
    test: tests/test_drafts.py::test_permissions_by_doctype
  - text: A rejected draft cannot be confirmed or rejected again.
    test: tests/test_drafts.py::test_failed_confirmation_can_be_retried_or_rejected
  - text: A draft cannot set what ERPNext sets itself, such as the document name or its submitted status.
    test: tests/test_drafts.py::test_clean_rejects_what_a_draft_may_not_set
  - text: A purchase order is not drafted for an item that has no earlier purchase order, because the supplier would be a guess.
    test: tests/test_ai_drafts.py::test_purchase_order_needs_a_known_supplier_and_permission
questions:
  - q: Confirming failed. What now?
    a: The draft is marked "failed" with the error from ERPNext. Choose *Confirm* again when ERPNext is back, or reject it.
  - q: Where is the purchase order after I confirm it?
    a: In ERPNext, as a draft. The *In ERPNext* link on the draft opens it; check it and submit it there.
  - q: Why do I not see a draft my colleague mentioned?
    a: You see only the kinds of drafts your role may make. Purchasing does not see customer messages, and sales does not see purchase orders.
---

Drafts are things prepared for you, by the assistant or by a person, that need a decision.

| Draft | When you confirm |
| --- | --- |
| Purchase order | A draft purchase order is created in ERPNext. Check it there and submit it. |
| Material request | A draft material request is created in ERPNext. |
| Supplier | The supplier is created in ERPNext. |
| Customer message | It is marked ready; copy it and send it yourself. |
| Nonconformance report | A nonconformance report is opened in Quality. |
| Quality inspection | A draft inspection is created in ERPNext for the receipt. |

Only people whose role allows it can confirm: buyers confirm purchase orders, material requests and suppliers,
sales confirms customer messages, Quality confirms reports and inspections. Reject a draft with a reason if it is wrong.
