---
title: Controlled documents and reading
group: Documents
order: 2
summary: Approval, taking effect, reading confirmations and periodic review.
video: document-control
try:
  - id: confirm-reading
    text: Sign in as **Lee** (Warehouse) and open *My reading* in the sidebar. Next to **QP-05** Receiving Inspection, type your password and choose *I have read and understood it*.
    to: /documents/control
    expect: the status of QP-05 changes from "pending" to "acknowledged".
    tour:
      - target: '[data-help="reading-mine"]'
        path: /documents/control
        text: What you are asked to read, with the day it is due. Open the document, read it, then confirm with your own password.
  - id: everyone
    text: Sign in as **Jordan** (Quality), open *My reading* and choose the *Everyone's reading* tab.
    to: /documents/control
    expect: QP-05 for Jordan and Lee, both acknowledged.
    tour:
      - target: '[data-help="reading-tabs"]'
        path: /documents/control
        text: My reading, Reviews due, Everyone's reading and Settings. The last three are for people who manage documents.
      - target: '[data-help="reading-everyone"]'
        text: Who has been asked to read what, with due days and status.
        elsewhere: Choose the Everyone's reading tab first.
  - id: readers
    text: Open **QP-08** Control of Nonconforming Product rev C from *Documents* (on the *To review* tab; choose *Confirm* first if it still waits there). Under *Who must read it*, tick **warehouse**, tick *This revision needs reading* and choose *Save*.
    to: /documents?tab=review
    expect: '"Saved." and, under the roles, how many people that is now: Lee is the only person in the warehouse role.'
    tour:
      - target: '[data-help="doc-readers"]'
        text: The roles and people who must read this revision. Set it before approval; the list carries to later revisions.
        elsewhere: Open QP-08 rev C and confirm it, so it is a draft.
  - id: send
    text: Choose *Send for approval*.
    expect: the status "waiting for approval" and the note that someone else approves it.
    tour:
      - target: '[data-help="doc-send"]'
        text: Save any corrections first. Whoever uploaded, confirmed or sent the document cannot approve it.
        elsewhere: Open QP-08 while it is a draft.
  - id: approve
    text: Sign in as **Sam** (Operations manager), open QP-08, leave *Takes effect on* empty, type your password and choose *Approve (sign)*.
    expect: '"Approved. The document is effective." Its file is frozen and the reading table lists Lee, due later.'
    tour:
      - target: '[data-help="doc-approve"]'
        text: A later day leaves time to read; until then the revision in effect stays. Leave it empty for today.
        elsewhere: Open QP-08 while it waits for approval.
      - target: '[data-help="doc-reading"]'
        text: The reading of this revision, one line per person, with the day it is due.
        elsewhere: Open QP-08 once it is effective.
      - target: '[data-help="doc-revise"]'
        text: Once it is effective, upload the next revision here, or make it obsolete with a reason.
        elsewhere: Open QP-08 once it is effective.
  - id: lee-reads
    text: Sign in as **Lee** and confirm QP-08 under *My reading*.
    to: /documents/control
    expect: QP-08 acknowledged, next to QP-05.
  - id: periodic
    text: Sign in as **Jordan**. Open *My reading*, then *Reviews due*, and open **QP-11** Calibration of Measuring Equipment.
    to: /documents/control
    expect: under *Periodic review*, a review "No change needed" by Jordan, approved by Dana, and the next review due 36 months after it.
    tour:
      - target: '[data-help="reading-reviews"]'
        text: Documents in effect whose type is reviewed periodically, by when the next review is due. Choose the Reviews due tab first.
        elsewhere: Choose the Reviews due tab on My reading.
      - target: '[data-help="doc-periodic-review"]'
        text: Record a review here (no change, a change, or postponed); someone other than the reviewer approves it with a password.
        elsewhere: Open QP-11 from Reviews due.
      - target: '[data-help="reading-settings"]'
        path: /documents/control
        text: How often each type of document is reviewed and how many days people have to read. Choose the Settings tab.
        elsewhere: Choose the Settings tab on My reading.
blocks:
  - text: A document is approved only with a password, by someone who did not upload, confirm or send it.
    test: tests/test_documents.py::test_controlled_document_approval_and_revision
  - text: Only one revision of a number is in effect; an older revision cannot be approved beside it.
    test: tests/test_documents.py::test_one_effective_revision_per_number
  - text: The day a revision takes effect cannot be before the day it is approved.
    test: tests/test_doc_control.py::test_planned_effect_and_reading
  - text: Only the person confirms their own reading, with their own password. A waiver needs a reason and someone else.
    test: tests/test_doc_control.py::test_planned_effect_and_reading
  - text: A periodic review is approved by someone other than the reviewer; "a change" must name the new revision and "postponed" needs a reason.
    test: tests/test_doc_control.py::test_periodic_review
  - text: Making a document obsolete needs a reason.
    test: tests/test_documents.py::test_controlled_document_approval_and_revision
questions:
  - q: Why can Dana not approve the demo procedures?
    a: Dana uploaded the demo folder, and whoever uploaded, confirmed or sent a document does not approve it. Sam can.
  - q: When does someone see a document under My reading?
    a: When the revision takes effect, if it was marked *This revision needs reading* and names them. It is due the number of days set for its type under *Settings*.
  - q: What happens to reading still open when a new revision takes effect?
    a: It is no longer asked for. The new revision asks the same people again.
---

- **Records, certificates and outside documents** are kept as soon as they are confirmed. Their file is frozen: it
  can never be replaced.
- **Procedures, work instructions and forms** become drafts. *Send for approval*; then someone who did not upload,
  confirm or send it approves it with their password. It becomes **effective** and its file is frozen.
- **A new revision**: on the effective document, upload the next revision. It goes through approval too; when it is
  approved, the old revision becomes obsolete automatically (and stays available).
- *Make obsolete* needs a reason. The history and signatures cannot be changed or deleted.

## Taking effect, reading and review

- **A planned day.** Whoever approves a revision can set the day it takes effect, to leave time for people to read
  it. Until then it is *approved, not yet in effect* and the revision it replaces stays in effect; on the day it
  takes effect by itself and the old one becomes obsolete.
- **Who must read it.** On a procedure, work instruction or form, choose the roles and people who must read it, and
  tick *This revision needs reading* before it takes effect (the list carries to later revisions). When it takes
  effect, each of them finds it under **My reading** in the sidebar (the *Reading and review* page), due a set number of days later, and confirms
  with their password that they have read and understood it. Nobody can confirm for someone else. Quality can waive
  someone's reading with a reason (not their own). When a newer revision takes effect, reading still open for the old
  one is no longer asked for. Overdue reading shows in the ISO training check.
- **Periodic review.** Each document type can be reviewed every so many months (procedures, work instructions and
  forms start at 36; change it under *My reading → Settings*). The next review is due that long after the document
  took effect or after its last approved review. On the document's page, record a review: no change, a change (name
  the new revision it started), or postponed (with the reason and a new date). Someone other than the reviewer
  approves it with a password; only then does the next due date move. *My reading → Reviews due* lists what is due
  and overdue.
