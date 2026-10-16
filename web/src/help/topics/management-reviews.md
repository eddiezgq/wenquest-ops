---
title: Management reviews
group: Regulated modules
order: 7
summary: Inputs counted from your records, the meeting, the chair signs.
needs: quality:view
try:
  - id: open-signed
    text: Open **MR-00001**, the signed demo review. Read the counted inputs and what the meeting wrote about them.
    to: /quality/reviews
    expect: the status "signed", the fingerprint under the inputs, Dana's signature at the bottom.
    tour:
      - target: '[data-help="reviews-list"]'
        text: Every review with its period, meeting date, chair and status. Open MR-00001.
  - id: start
    text: Sign in as **Jordan** (Quality). Choose *New review*, keep this year as the period and choose *Start*.
    to: /quality/reviews
    expect: a new draft review page.
    tour:
      - target: '[data-help="new-review"]'
        text: Starts a review. Only the owner and Quality can.
      - target: '[data-help="review-period"]'
        click: '[data-help="new-review"]'
        text: The period the inputs are counted for. It is fixed once the inputs are collected.
  - id: collect
    text: Choose *Collect the inputs*.
    expect: thirteen boxes of figures, "unknown" where there are no records to count, and a fingerprint.
    tour:
      - target: '[data-help="review-collect"]'
        text: Counts every input from the records of the period and freezes them. Count again any time before it is signed; the old fingerprint stays in the history.
        elsewhere: Open your new review first (Management reviews, then its number).
      - target: '[data-help="review-inputs"]'
        text: The inputs, one box each. Under each, the meeting writes its assessment.
  - id: meeting
    demo: /quality/reviews/1
    text: Fill in the meeting date (today), the attendees, the chair (**Dana**), an assessment under at least one input and the conclusion. Choose *Save*.
    expect: '"Saved." and, at the bottom, what is still needed before signing.'
    tour:
      - target: '[data-help="review-meeting"]'
        text: The meeting date, the chair who signs and who attended.
        elsewhere: Open your new review first.
      - target: '[data-help="review-conclusion"]'
        text: Is the quality system suitable, adequate and effective? Then Save.
  - id: action
    demo: /quality/reviews/1
    text: Add an action with an owner (for example Pat) and a due date in a few weeks.
    tour:
      - target: '[data-help="review-actions"]'
        text: What the meeting decided, each with an owner and a date. Owners mark them done later, with evidence.
        elsewhere: Open your new review first.
  - id: chair-signs
    text: Sign out, sign in as **Dana**, open the review and sign it with your password.
    expect: the status "signed"; the review can no longer be changed.
    tour:
      - target: '[data-help="review-sign"]'
        text: Only the chair sees the password box, and only when nothing is missing.
        elsewhere: Open the review as Dana first.
  - id: iso
    text: Open *Quality system* and look at the management review control point.
    to: /system
    expect: it is met, with your review as the evidence (a link to it).
blocks:
  - text: Whoever collected the inputs, wrote an assessment or the conclusion, or added an action cannot sign as the chair.
    test: tests/test_review.py::test_whoever_prepared_it_does_not_sign
  - text: Only the chair signs, with their own password, and only once the meeting date, attendees, an assessment and the conclusion are written.
    test: tests/test_review.py::test_review_from_inputs_to_signature
  - text: A meeting date in the future, or before the period starts, is refused.
    test: tests/test_review.py::test_review_from_inputs_to_signature
  - text: Once the inputs are collected the period cannot change; inputs changed behind the review's back are not signed.
    test: tests/test_review.py::test_review_from_inputs_to_signature
  - text: A signed review, and the actions it decided, cannot be changed or deleted, not even in the database.
    test: tests/test_review.py::test_review_from_inputs_to_signature
  - text: An action is marked done only by its owner or Quality, and only with what shows it is done.
    test: tests/test_review.py::test_review_from_inputs_to_signature
questions:
  - q: Why does a figure say "unknown"?
    a: There were no records to count it from in the period, for example no lots inspected. WenQuest Ops never shows 0 for that.
  - q: I collected the inputs and then new records came in. What now?
    a: Choose *Count again* before signing. The new fingerprint replaces the old one, which stays in the history.
  - q: Can I still use the management review register?
    a: Yes. Reviews held outside WenQuest Ops can still be entered there; signed reviews from this page appear in it on their own.
---

*Management reviews* in the sidebar is where top management reviews the quality system at planned intervals. Start a
review with a title and the period it covers, then choose *Collect the inputs*. WenQuest Ops counts them from your
records for that period: incoming inspection, nonconformances, corrective actions, suppliers, documents and reading,
complaints, measuring equipment, changes, risk, production, recalls, delivery performance, and the actions of earlier
reviews still open. A figure that cannot be counted shows "unknown", not 0. The inputs are then frozen with a
fingerprint; records made later do not change them unless someone counts again, and the old fingerprint stays in the
history.

At the meeting, write the date, who attended, the meeting's assessment next to each input and the conclusion: is the
system suitable, adequate and effective? Add the actions decided, each with an owner and a due date. The chair signs
with their password once all this is written. The chair must not be someone who collected the inputs or wrote the
notes or actions. Once signed the review is fixed and goes into the management review register that the ISO check
reads. Owners mark their actions done with what shows it is done; the next review lists those still open.
*Print the report* gives the review on paper.
