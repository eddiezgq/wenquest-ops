---
title: Nonconformance reports and 8D
group: Quality
order: 1
summary: Report, contain, decide what to do with the product, sign.
video: nonconformances
needs: quality:view
try:
  - id: open-list
    text: Sign in as **Jordan** (Quality). Open *Quality* and stay on the *Nonconformances* tab.
    to: /quality?tab=ncrs
    expect: NCR-00001, the major report for the rejected HX-BOLT-M8 lot, with the status "dispositioned".
    tour:
      - target: '[data-help="quality-tabs"]'
        text: Nonconformances, corrective actions, incoming inspection, supplier quality, control charts and the workflows.
      - target: '[data-help="quality-list"]'
        text: The open reports. Use *Show* above the list to see closed or cancelled ones.
  - id: open-demo
    demo: /quality/ncr/1
    text: Open **NCR-00001**. Read what was done to contain the lot and the disposition (return to supplier).
    expect: 'a box on the right that says "A major report closes when a linked corrective action is closed", and CAPA-00001 under corrective actions.'
    tour:
      - target: '[data-help="ncr-next-step"]'
        text: The next step for this report. It changes as the report moves on.
        elsewhere: Open NCR-00001 first (Quality, Nonconformances).
  - id: try-close
    text: While **CAPA-00001** is still open, write a closing note, enter your password and choose *Close (sign)*.
    expect: '"NCR-00001 is major: it closes when a linked corrective action is closed". Nothing is signed.'
  - id: new
    text: Go back to *Quality* and choose *New nonconformance*. Give a title (for example **Crushed boxes**), a description, *Minor*, item **BOX-12** and quantity **20**. Choose *Open the report*.
    to: /quality?tab=ncrs
    expect: a new report with the status "open" and you as the owner.
    tour:
      - target: '[data-help="ncr-new"]'
        text: Opens the form. Only people who may record quality work see it.
      - target: '[data-help="ncr-form"]'
        click: '[data-help="ncr-new"]'
        text: A major report needs a corrective action before it closes.
  - id: contain
    text: Write what was done so the boxes go no further (for example **Set aside on the receiving bench**) and choose *Save containment*.
    expect: the status "contained" and a *Disposition* box.
  - id: concession
    demo: /quality/ncr/2
    text: Choose the disposition *Use as is (concession) (needs approval)*, quantity **20** and a reason. Choose *Submit disposition*.
    expect: 'the status "pending approval" and "You submitted it; someone else must approve it."'
    tour:
      - target: '[data-help="ncr-next-step"]'
        text: You submitted the disposition, so you cannot approve it here.
        elsewhere: Open your new report first.
  - id: approve-close
    demo: /quality/ncr/1
    text: Sign out and sign in as **Sam** (Operations manager). Open the report, enter your password and choose *Approve (sign)*. Then write a closing note, enter your password again and choose *Close (sign)*.
    expect: the status "closed" and two signatures, "Disposition approved" and "Nonconformance closed".
    tour:
      - target: '[data-help="ncr-signatures"]'
        text: Every signature with the name, time and meaning. They cannot be changed or deleted.
        elsewhere: Open the report first.
blocks:
  - text: Whoever submitted a disposition that needs approval cannot approve it; someone else signs with their own password.
    test: tests/test_quality.py::test_concession_needs_another_persons_signed_approval
  - text: A major report does not close until a linked corrective action is closed.
    test: tests/test_quality.py::test_capa_stages
  - text: A disposition must be one of the company's types, give a reason and cover no more than the report's quantity. Steps out of order are refused.
    test: tests/test_quality.py::test_ncr_without_approval
  - text: An inspection gets only one nonconformance report.
    test: tests/test_quality.py::test_ncr_without_approval
  - text: A closed report cannot be cancelled, and its 8D cannot change.
    test: tests/test_quality.py::test_ncr_without_approval
  - text: An 8D is marked complete only when all eight sections are written, with your password; after that it cannot change.
    test: tests/test_quality.py::test_8d_is_signed
questions:
  - q: Where do reports come from?
    a: A rejected incoming inspection opens one automatically, both one rejected in ERPNext and a lot rejected under *Incoming inspection*. You can also open one by hand with *New nonconformance*.
  - q: Which dispositions need approval?
    a: By default return to supplier, rework / sort and scrap need none. *Use as is (concession)* needs approval by someone other than the person who submitted it. The types are configuration.
  - q: A report says "severity unknown". What do I do?
    a: Reports brought in from an old ledger may have no severity. Choose *Minor* or *Major* on the report; it cannot close until you do.
  - q: Can I delete a report?
    a: No. Cancel it with a reason. The report, its history and its signatures stay.
---

![A nonconformance report](img/quality-ncr.webp)

*Quality* in the sidebar opens on the *Nonconformances* tab. A rejected inspection opens a report automatically; you
can also open one by hand with *New nonconformance*. The box on the right of a report always shows its next step.

1. **Contain**: what was done so bad parts go no further (for example, moved to QC Hold).
2. **Disposition**: return to supplier, rework / sort, scrap, or use as is (concession), with quantity and reason.
   Types that need approval (such as *use as is*) must be approved by **someone else**, with their password.
3. **Close**: signed with your password. A *major* report closes only after its corrective action is closed.

Reports can be cancelled with a reason. Nothing is deleted.

## 8D

Write the eight sections on the report and choose *Save 8D*. *Mark 8D complete (sign)* signs it; after that it cannot
change.

## Corrective actions

*Open corrective action* at the bottom of a report starts a corrective or preventive action linked to it. A report has
one open corrective action at a time.
