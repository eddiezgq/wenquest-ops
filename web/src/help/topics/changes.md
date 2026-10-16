---
title: Changes
group: Regulated modules
order: 3
summary: Assess, approve, implement and check a change.
needs: quality:view
try:
  - id: open-closed
    text: Open *Changes*, set the list to *Closed* and open **Second source for M8 bolts**. Read the four answers, the implementation and the effectiveness check.
    to: /quality/changes
    expect: the status "closed" and two signatures, the approval and the closing.
    tour:
      - target: '[data-help="changes-list"]'
        text: Every change with its kind, status, owner and target date. Choose Open, Closed, Cancelled or All above the list.
  - id: draft
    text: Set the list back to *Open* and open the draft **New label printer for shipping**.
    to: /quality/changes
    expect: under the buttons, "To submit" and what is still missing, such as why and the answers to the four questions.
    tour:
      - target: '[data-help="change-assess"]'
        text: Four questions a person answers. A yes to the regulatory question needs the regulatory decision; a yes to validation needs the plan.
        elsewhere: Open the draft change first.
  - id: refused
    demo: /quality/changes/2
    text: Sign in as **Jordan** (Quality). Open **Move QC Hold to the mezzanine cage**, which Jordan raised and submitted, and try to approve it with your password.
    expect: a refusal. Someone who did not raise, own, submit or edit the change approves it.
    tour:
      - target: '[data-help="change-steps"]'
        text: Approve with a password, or send it back as a draft with what needs to change.
        elsewhere: Open the submitted change first.
  - id: approve
    text: Sign out, sign in as **Dana** (Owner), open the same change and approve it with your password.
    expect: the status "approved" and Dana's signature.
  - id: implement
    demo: /quality/changes/1
    text: Sign in as **Sam** (Operations manager), the owner. Write how it was implemented, choose *Save*, then *Mark implemented*.
    expect: the status "implemented" and an *Effectiveness check* box.
    tour:
      - target: '[data-help="change-impl"]'
        text: The new revision of each document it changes, the validation result when needed, and how it was implemented.
        elsewhere: Open the approved change first.
  - id: effectiveness
    text: Write the effectiveness check and choose *Save*.
    expect: '"Saved." Sam cannot close the change, as its owner.'
  - id: close
    text: Sign in as **Jordan** and choose *Close (sign)* with your password.
    expect: the status "closed".
blocks:
  - text: A change is not submitted while what changes, why, the owner, the assessment or an answer to the four questions is missing.
    test: tests/test_change_control.py::test_change_from_draft_to_closed
  - text: Once submitted, what was assessed cannot be changed, not even in the database. Only the target date can move, and every move is logged.
    test: tests/test_change_control.py::test_change_from_draft_to_closed
  - text: Whoever raised, owns, submitted or edited a change cannot approve it.
    test: tests/test_change_control.py::test_send_back_and_cancel
  - text: A change is not marked implemented until the new revision of each document it changes is approved after the change and in effect, and the validation result is written when needed.
    test: tests/test_change_control.py::test_change_from_draft_to_closed
  - text: Closing needs the effectiveness check and someone other than the owner. A closed change cannot be changed or deleted.
    test: tests/test_change_control.py::test_change_from_draft_to_closed
  - text: Once a new revision it brings is in effect, a change cannot be cancelled; it is implemented and closed instead.
    test: tests/test_change_control.py::test_change_from_draft_to_closed
questions:
  - q: Quality sent my change back. What now?
    a: It is a draft again with the reason in the history. Make the changes and submit it again. Whoever edited it then cannot approve it.
  - q: Can the target date still move after submitting?
    a: Yes. The target date can move until the change is closed, and every move is logged.
  - q: Which documents can a change name?
    a: Only documents in effect. It is implemented once a new revision of each one, approved after the change, is in effect.
---

**Changes** records changes to a product, process, supplier, document, software or equipment. Raise one as a draft:
what changes, why, its owner, the documents in effect it changes, and four questions a person answers (does it affect
product already released; could it need a regulatory submission or notification; does the risk file need updating;
does it need verification or validation first). A yes to the regulatory question needs the regulatory decision; a yes
to validation needs the plan. Submitting fixes what was assessed (Quality can send it back with a reason; the target
date can still move, and every move is logged). Someone who did not raise, own, submit or edit the change approves
it with a password. It is marked implemented once the new revision of each document it changes is in effect and,
when needed, the validation result is written; someone other than the owner closes it with a password after the
effectiveness check. A change is cancelled with a reason before it is implemented; nothing is deleted.
