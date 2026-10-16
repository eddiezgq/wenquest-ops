---
title: Complaints
group: Regulated modules
order: 1
summary: Receive, investigate, assess reportability, answer, close.
needs: quality:view
try:
  - id: open-closed
    text: Open *Complaints* and set the list to *Closed*. Open the complaint about two cracked duplex outlets and read how it was investigated, decided and answered.
    to: /quality/complaints
    expect: the status "closed", "Need not be reported" with the reason, and two signatures (Jordan's decision, Dana's closing).
    tour:
      - target: '[data-help="complaints-list"]'
        text: Every complaint with when it was received, the product, whether anyone was hurt, its status and reporting. Choose Open, Closed, Cancelled or All above the list.
  - id: record
    text: Sign in as **Sam** (Operations manager). Choose *Record a complaint*, fill in the customer and what happened, and choose *Record*.
    to: /quality/complaints
    expect: a new complaint page with the status "new" and, under the buttons, what is still needed to start the investigation.
    tour:
      - target: '[data-help="complaints-new"]'
        text: Records a new complaint. People who can record quality work see it.
      - target: '[data-help="complaints-form"]'
        click: '[data-help="complaints-new"]'
        text: When it was received and when the company first knew, from whom, the product, what happened, whether anyone was hurt and whether the product failed.
  - id: start
    text: Set yourself as the owner, the product (for example **OUTLET-DUP**) and *Anyone hurt?* to **no**. Choose *Save*, then *Start the investigation*.
    expect: the status "investigation", and the boxes for the root cause, the investigation and the reply to the customer.
    tour:
      - target: '[data-help="complaint-details"]'
        text: The owner, the product and whether anyone was hurt are needed before the investigation starts.
        elsewhere: Open your new complaint first (Complaints, then its number).
      - target: '[data-help="complaint-start"]'
        text: Starts the investigation once nothing is missing and everything is saved.
        elsewhere: Open your new complaint first.
  - id: investigate
    text: Write the root cause and the investigation and conclusion. Choose *Save*.
    expect: '"Saved."'
  - id: decide
    text: Sign out and sign in as **Jordan** (Quality). Open the complaint, answer the three questions **no**, choose *need not be reported*, give the reason and sign with your password.
    expect: the status "assessed"; the investigation and the answers can no longer be changed.
    tour:
      - target: '[data-help="complaint-assess"]'
        text: Someone other than the owner answers the three questions and decides. A yes shows that this usually means reporting, and the deadline.
        elsewhere: Open the complaint as Jordan first.
  - id: close
    text: Write the reply to the customer and choose *Save*. Then sign *Close (sign)* with your password.
    expect: the status "closed" and Jordan's two signatures.
    tour:
      - target: '[data-help="complaint-close"]'
        text: What is still needed is listed here. Someone other than the owner closes it.
        elsewhere: Open the complaint as Jordan first.
blocks:
  - text: A date after today is refused, and so is a day the company first knew that comes after the day the complaint was received.
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: The investigation does not start without an owner, the product and whether anyone was hurt.
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: The owner neither decides on reporting nor closes the complaint. Someone else does, with their own password, and only after the investigation's conclusion is written and all three questions are answered.
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: Once decided, the investigation and the decision cannot be changed, not even in the database.
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: A complaint is not closed while the report's reference (when it must be reported) or the reply to the customer is missing; a closed complaint cannot be changed or deleted.
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: A duplicate is cancelled only with a reason, and not investigating needs a reason approved by someone other than the owner.
    test: tests/test_complaints.py::test_exceptions_no_investigation_and_cancel
questions:
  - q: Does WenQuest Ops decide whether a complaint must be reported?
    a: No. It asks three questions and, when one is answered yes, shows that this usually means reporting and the deadline. A person decides and signs. A yes with a decision not to report is allowed with the reason and counted as an exception.
  - q: Where do the reporting deadlines come from?
    a: They are the company's settings, counted from the day the company first knew. Set them to what your regulations require.
  - q: Can I open a nonconformance or a corrective action from a complaint?
    a: Yes. *Open a nonconformance* and *Open a corrective action* are on the complaint page while it is open.
---

**Complaints** in the sidebar records each complaint: when it was received and when the company first knew, from
whom, the product, what happened, whether anyone was hurt and whether the product failed. Give it an owner and start
the investigation; record the root cause and the conclusion (or Quality approves not investigating, with the reason).

Someone other than the owner then decides, with a password, whether it must be reported to a regulator. WenQuest
Ops asks three questions (harm, a malfunction that could cause harm if it happened again, a recall or correction)
and, when one is answered yes, shows that this usually means reporting and the deadline counted from the day the
company first knew. It never decides: a yes with a decision not to report is allowed with its reason and counted as
an exception. The deadlines are the company's settings; set them to what your regulations require. Reports are made
outside WenQuest Ops; enter their reference and date here. Once decided, the investigation and the decision cannot
change.

Someone other than the owner closes the complaint with a password once everything is there (the conclusion, the
report if one was due, the reply to the customer); WenQuest Ops lists what is missing all at once. A nonconformance
report or a corrective action can be opened from a complaint. A duplicate is cancelled with a reason; nothing is
deleted. The ISO complaint checks read these complaints as well as the complaints register.
