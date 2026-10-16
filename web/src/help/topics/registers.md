---
title: Registers
group: Quality system
order: 2
summary: Training, audits, objectives, risks and other records the standard asks for.
video: registers
needs: quality:view
try:
  - id: open
    text: Sign in as **Jordan** (Quality). On *Quality system*, open *Training and competence* in the *Registers* box.
    to: /system/registers/training
    expect: the demo entries for Lee Warehouse (QP-05 Receiving Inspection) and Pat Buyer (QP-04 Purchasing), both "recorded".
    tour:
      - target: '[data-help="qms-registers"]'
        path: /system
        text: One box per register, with its number of entries. Shown once a standard is adopted.
        elsewhere: Adopt a standard on Quality system first, or use Take me there.
      - target: '[data-help="register-entries"]'
        path: /system/registers/training
        text: Every entry, newest first. Void entries are hidden unless you tick Show void entries.
  - id: record
    text: 'Record an entry: Person **Lee Warehouse**, Training or skill **WI-WH-03 Picking and Packing**, today''s date and Result *competent*. Choose *Record*.'
    to: /system/registers/training
    expect: '"Entry recorded." and the new entry at the top.'
    tour:
      - target: '[data-help="register-form"]'
        path: /system/registers/training
        text: The register's fields; those with a red star are needed. Empty fields stay unknown.
  - id: change
    text: Choose *Change* on your entry, fill in Trainer or assessor **Sam Ops** and choose *Save changes*.
    expect: '"Entry changed." Training entries stay open to change; they are not approved with a password.'
  - id: audits
    text: Open the internal audits register.
    to: /system/registers/audits
    expect: the demo audit of Receiving by Sam Ops, "approved" by Dana, with no *Change* button.
  - id: approve
    text: Record an audit of **Shipping** by **Sam Ops** with today's date. Choose *Approve* on it, type your password and choose *Approve (sign)*.
    to: /system/registers/audits
    expect: '"Approved and locked." and your name under "approved".'
  - id: void
    text: Choose *Void* on that audit, write the reason "Entered for practice", type your password and choose *Void the entry*.
    to: /system/registers/audits
    expect: '"Entry void." The entry is hidden; tick *Show void entries* to see it struck through, with the reason.'
blocks:
  - text: An entry missing a field marked as needed is refused.
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
  - text: An approved entry cannot be changed, not even in the database; void it with a reason and record a new one.
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
  - text: Voiding needs a reason, and voiding an approved entry also needs your password.
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
  - text: Only internal audits and management reviews are approved with a password; training entries cannot be.
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
  - text: No entry is deleted; every change is kept in its history.
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
questions:
  - q: Why does a check say "unknown" for a register?
    a: The register is empty. It stays unknown until you start using it; it is never counted as met.
  - q: Can I bring in my old training matrix?
    a: 'Yes. Upload it under *Documents*, open it and import it as "Register: Training and competence". Rows of signed registers, such as old management reviews, come in approved by the signed import.'
  - q: Where do complaints, calibrations and management reviews go now?
    a: They have their own pages in the sidebar. The checks read those records together with the register entries.
---

The standard also asks for records that are not nonconformances or documents. *Quality system* has a register for
each: training and competence, measuring equipment and calibration, internal audits, management reviews, quality
objectives, risks and opportunities, customer feedback and complaints, and supplier approval. Open one from the
*Registers* box (shown once a standard is adopted), record entries with the form, and change them while they are
open. Internal audits and management reviews are approved with your password and then locked. A wrong entry is voided with a reason; nothing is deleted
and every change is kept.

The checks read the registers: training not expired or followed up, equipment calibrated and not due, an approved
internal audit and management review within the set number of days, each objective and risk reviewed in time,
complaints answered in time, and every supplier you bought from in the last year approved. The numbers of days are
under *Settings*. An empty register gives "unknown" until you start using it.

Complaints, measuring equipment and management reviews also have their own pages in the sidebar (*Complaints*,
*Measuring equipment*, *Management reviews*). The checks read the records made there together with the entries of
the matching register, so a record made on its own page is not entered again in the register.

An old spreadsheet, such as a training matrix or a calibration log, comes in like a nonconformance log: upload it
under *Documents*, open it and import it as "Register: …". The columns are matched to the register's fields for you
to check before the signed import.
