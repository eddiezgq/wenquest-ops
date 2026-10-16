---
title: Quality system
group: Quality system
order: 1
summary: Check the company against ISO 9001 or ISO 13485.
video: quality-system
needs: quality:view
try:
  - id: adopt
    text: Sign in as **Jordan** (Quality) and open *Quality system* in the sidebar. Choose **ISO 9001**, keep the edition *ISO 9001:2015 (with Amendment 1:2024)*, type your password and choose *Adopt the standard (sign)*.
    to: /system
    expect: '"Adopted and checked against your records." and the control points by process, each met, not met or unknown.'
    tour:
      - target: '[data-help="qms-standards"]'
        text: Switches between ISO 9001 and ISO 13485. Both read the same records.
      - target: '[data-help="qms-adopt"]'
        text: Only the owner or Quality adopts a standard, with their password. Editions not checked yet cannot be chosen.
        elsewhere: The standard is already adopted; the page shows its control points instead.
  - id: filter
    text: Choose *not met* in the row of counts and read the first control point.
    to: /system
    expect: what is wrong, and the records behind it as links.
    tour:
      - target: '[data-help="qms-filter"]'
        text: Show all control points, or only those not met, unknown, met or that do not apply.
        elsewhere: Adopt the standard first.
      - target: '[data-help="qms-process"]'
        text: One box per process. Each control point says the clauses, the result and the records it rests on.
  - id: not-apply
    text: Choose *All*, find the point on design and development and choose *Change*. Write the reason "We distribute; we do not design products", type your password and choose *Does not apply (sign)*.
    to: /system
    expect: '"Recorded: it does not apply." and the point shown as "does not apply".'
  - id: settings
    text: In *Settings* at the bottom, change *Days to contain a nonconformance* from **7** to **10**. Then set it back to 7.
    to: /system
    expect: '"Setting saved and checked again." each time, and the default shown next to a changed value.'
    tour:
      - target: '[data-help="qms-settings"]'
        text: Your company's numbers of days, and our own rules, which you can switch off and replace with your procedure.
        elsewhere: Adopt the standard first.
  - id: check-now
    text: Choose *Check now* at the top.
    to: /system
    expect: '"Checked again against your records." and a new line under *Earlier checks*.'
    tour:
      - target: '[data-help="qms-check-now"]'
        text: Runs the check at once. It also runs every day and whenever something is declared or linked.
        elsewhere: Adopt the standard first.
      - target: '[data-help="qms-history"]'
        text: Every check is kept. Open one to see the system as it was that day.
  - id: registers
    text: In the *Registers* box, open *Training and competence*.
    to: /system
    expect: the register page with the demo entries for Lee and Pat.
    tour:
      - target: '[data-help="qms-registers"]'
        text: The records the standard asks for that are not nonconformances or documents. The checks read them.
        elsewhere: Adopt the standard first.
blocks:
  - text: Adopting a standard needs the password of the owner or Quality, and an edition not checked yet is refused.
    test: tests/test_qms.py::test_adopting_declaring_linking_and_evaluating
  - text: Saying a requirement does not apply needs a reason and your password; requirements that always apply cannot be left out.
    test: tests/test_qms.py::test_adopting_declaring_linking_and_evaluating
  - text: A document is linked only once it is confirmed in the library, and counts only while it is in effect; a draft or an obsolete one is not met.
    test: tests/test_qms.py::test_document_checks_and_declarations
  - text: A number of days must be a whole number from 0 to 365.
    test: tests/test_qms.py::test_adopting_declaring_linking_and_evaluating
  - text: Earlier checks, adopted standards, declarations and settings are kept as they were; they cannot be changed or deleted, not even in the database.
    test: tests/test_qms.py::test_adopting_declaring_linking_and_evaluating
questions:
  - q: Why are so many points unknown?
    a: There is nothing to judge yet, for example no reports in the last year or an empty register. Unknown is never counted as met.
  - q: Does WenQuest Ops certify the company?
    a: No. Certification is for a certification body. The requirement summaries are our own words, not the standard's text.
  - q: If I adopt both standards, do I enter records twice?
    a: No. Both read the same records; settings and what does not apply are kept per standard.
---

*Quality system* in the sidebar checks your company against a standard: ISO 9001, or ISO 13485 for medical devices, or both.
WenQuest Ops turns the standard into control points, things your records must be able to show, and checks each one
against what is in the system: nonconformance reports, corrective actions, incoming inspections, the registers and the
document library. The buttons at the top of the page switch between the standards; both read the same records, so a
complaint or a calibration is entered once.

![The quality system checked against ISO 9001](img/quality-system.webp)

## Adopt the standard

The owner or Quality chooses the edition and adopts the standard with their password. ISO 9001:2015 is available now;
ISO 9001:2026 follows once its clause references have been checked against the published text. For ISO 13485,
ISO 13485:2016 is available; the extra requirements of the FDA's Quality Management System Regulation (21 CFR 820,
which takes in ISO 13485:2016) will be added later. The requirement
summaries are our own words, not the standard's text, and WenQuest Ops does not certify anyone: certification is
for a certification body.

## Met, not met, unknown

Each control point shows one of:

- **met**: the records show it, with links to them;
- **not met**: the records show a gap, listed with each record and what is wrong, for example a major
  nonconformance without a corrective action, or a concession approved by the person who proposed it;
- **unknown**: there is nothing to judge yet, for example no reports in the last year, or the evidence comes from a
  register that is not there yet. Unknown is never counted as met;
- **does not apply**: the company declared it, with a reason.

The check looks at records still open and at those closed in the last year. It runs again every day (with the
background job that also pulls changes from ERPNext), whenever someone who edits quality records chooses *Check now*,
and when you declare something or link a document. Every check is kept: *Earlier checks* shows what the system looked
like on a given day. Records imported from old spreadsheets that were already closed are counted as history, not
judged, because they were not made under these rules; imported records still open are judged like any other.

Where WenQuest Ops checks a requirement with a rule of its own, for example "every major nonconformance gets a
corrective action within 14 days" or "a concession is approved by someone other than the person who proposed it",
the control point says so. These rules are one way to show the requirement is met; the standard itself allows others.
Under *Settings* at the bottom of the page you can change the numbers of days, or switch one of these rules off and
link your own procedure for that control point instead. Changes are recorded and the system is checked again.

## Say what does not apply, link documents

Some requirements may not apply to your company, such as design and development when you only distribute. Choose
*Change* on the control point, give the reason and sign with your password. Others are shown by a document, such as
the scope statement, the quality policy or a process map: link a document from the library. It counts while it is in
effect: approved, for procedures, work instructions and forms; confirmed and not obsolete, for other documents such as
a policy kept as a record. The scope is met when the scope statement is linked and every requirement that may not
apply has been declared one way or the other.
