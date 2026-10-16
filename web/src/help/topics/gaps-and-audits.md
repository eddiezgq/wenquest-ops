---
title: Gap report and audit checklist
group: Quality system
order: 3
summary: What is missing, a to-do for each gap, and the audit checklist.
needs: quality:view
try:
  - id: open
    text: Sign in as **Jordan** (Quality). On *Quality system*, choose *Gap report*. Adopt ISO 9001 first if the button is not there (see *Quality system*).
    to: /system/gaps
    expect: how many points are not met or unknown, and the gaps by process with the records behind them.
    tour:
      - target: '[data-help="qms-gaps"]'
        path: /system
        text: Shown once a standard is adopted.
        elsewhere: Adopt a standard on Quality system first.
      - target: '[data-help="gaps-summary"]'
        path: /system/gaps
        text: The counts from the latest check. A to-do is closed by the check once its point is met.
  - id: todo
    text: On the first gap, write the owner **Dana**, pick a due date in a month and choose *Add a to-do*.
    to: /system/gaps
    expect: '"To-do:" with its title, Dana and the due date, in place of the form.'
    tour:
      - target: '[data-help="gaps-todo"]'
        path: /system/gaps
        text: Each gap has this box. Give it a to-do with an owner and a due date, change it later, mark it done or drop it.
        elsewhere: The gap report lists control points once a standard is adopted (Quality system).
  - id: all
    text: Choose *A to-do for every gap*.
    to: /system/gaps
    expect: every gap now has a to-do; the count "with a to-do" matches the gaps.
    tour:
      - target: '[data-help="gaps-todo-all"]'
        path: /system/gaps
        text: One to-do for each gap that has none yet.
        elsewhere: This appears once a standard is adopted and has gaps.
  - id: drop
    text: On one to-do, write a note such as "Covered by QP-04" and choose *Drop*. Then tick *Show closed to-dos*.
    to: /system/gaps
    expect: '"To-do dropped." The gap can get a new to-do, and the dropped one is listed with your note.'
    tour:
      - target: '[data-help="gaps-closed"]'
        path: /system/gaps
        text: Closed to-dos are kept, with who closed them and why.
        elsewhere: This appears once a to-do has been made from a gap.
  - id: checklist
    text: Go back to *Quality system* and choose *Audit checklist*. Choose the process *Externally provided products and services*.
    to: /system/audit
    expect: questions for the auditor, each with what the records show, a sample of records to look at and the gaps found.
    tour:
      - target: '[data-help="qms-audit"]'
        path: /system
        text: Shown once a standard is adopted.
        elsewhere: Adopt a standard on Quality system first.
      - target: '[data-help="audit-process"]'
        path: /system/audit
        text: All processes, or one at a time.
      - target: '[data-help="audit-questions"]'
        path: /system/audit
        text: Print it and take it to the audit. Each question has room for the auditor's notes.
  - id: record-audit
    text: Choose *Record the audit in the internal audits register*.
    to: /system/audit
    expect: the internal audits register, where the audit and its findings are recorded and then approved with a password.
    tour:
      - target: '[data-help="audit-register"]'
        path: /system/audit
        text: After the audit, record it here (see *Registers*).
        elsewhere: The checklist appears once a standard is adopted (Quality system).
blocks:
  - text: A gap has one open to-do at a time.
    test: tests/test_gaps.py::test_gaps_and_todos
  - text: Dropping a to-do needs a reason; a closed to-do cannot be changed or deleted, not even in the database.
    test: tests/test_gaps.py::test_gaps_and_todos
  - text: The gap report waits until a standard is adopted, and people who may only look cannot add to-dos or ask for drafts.
    test: tests/test_gaps.py::test_gaps_api
  - text: A document the AI drafts is not in effect until it is confirmed and then approved, with a password, by someone who did not ask for it, confirm it or send it.
    test: tests/test_gaps.py::test_the_model_drafts_a_missing_document
  - text: A draft with no text, or cut off, is not stored.
    test: tests/test_gaps.py::test_the_model_drafts_a_missing_document
questions:
  - q: Why is there no *Draft the document with AI* button?
    a: It needs the company's model key, the right to adopt standards, and a gap shown by a document, such as the quality policy.
  - q: Do I have to close to-dos myself?
    a: No. When a later check finds the point met, the check closes the to-do. You can also mark it done or drop it with a reason.
---

*Gap report* (on the *Quality system* page) lists every control point not met or unknown, by process, with the records behind it. Give each a to-do
with an owner and a due date, or choose *A to-do for every gap*. When a later check finds the point met, the to-do
is closed by the check itself; you can also mark it done, or drop it with a reason. Closed to-dos are kept.

Where a document is missing, such as the quality policy, people who adopt standards can choose *Draft the document
with AI* (with the company's model key). The draft goes into *Documents* marked as a draft written by AI, with
"[to fill: ...]" wherever it needs your facts and a list of what to fill in. It is not in effect until you review it,
confirm it and someone approves it; then link it to the control point.

## Internal audit checklist

*Audit checklist* turns the control points of a process into questions for the auditor, each with what the records
show, a sample of records to look at and the gaps found. Print it, take it to the audit, and record the audit and
its findings in the internal audits register.
