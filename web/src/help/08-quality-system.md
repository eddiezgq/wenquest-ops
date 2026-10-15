# Quality system

*Quality system* checks your company against a standard, starting with ISO 9001. WenQuest Ops turns the standard into
control points, things your records must be able to show, and checks each one against what is in the system:
nonconformance reports, corrective actions, incoming inspections and the document library.

![The quality system checked against ISO 9001](img/quality-system.webp)

## Adopt the standard

The owner or Quality chooses the edition and adopts the standard with their password. ISO 9001:2015 is available now;
ISO 9001:2026 follows once its clause references have been checked against the published text. The requirement
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

## Registers

The standard also asks for records that are not nonconformances or documents. *Quality system* has a register for
each: training and competence, measuring equipment and calibration, internal audits, management reviews, quality
objectives, risks and opportunities, customer feedback and complaints, and supplier approval. Open one from the
*Registers* box, record entries with the form, and change them while they are open. Internal audits and management
reviews are approved with your password and then locked. A wrong entry is voided with a reason; nothing is deleted
and every change is kept.

The checks read the registers: training not expired or followed up, equipment calibrated and not due, an approved
internal audit and management review within the set number of days, each objective and risk reviewed in time,
complaints answered in time, and every supplier you bought from in the last year approved. The numbers of days are
under *Settings*. An empty register gives "unknown" until you start using it.

An old spreadsheet, such as a training matrix or a calibration log, comes in like a nonconformance log: upload it
under *Documents*, open it and import it as "Register: …". The columns are matched to the register's fields for you
to check before the signed import.

## Coming next

A gap report and an internal audit checklist made from the records, and setting the system up from your own
procedures.
