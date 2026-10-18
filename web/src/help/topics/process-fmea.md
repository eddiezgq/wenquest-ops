---
title: Process FMEA
group: Quality
order: 9
summary: Failure modes of a process with severity, occurrence and detection on your own scales; RPN computed; approved by someone else and kept.
needs: quality:view
try:
  - id: criteria
    text: 'Sign in as **Jordan** (Quality). Open *Process FMEA* and look at *The company''s FMEA criteria*.'
    to: /quality/fmea
    expect: the demo company's own words for ranks 1 to 10 of severity, occurrence and detection, and its rule - action when RPN is at least 100 or severity at least 9.
    tour:
      - target: '[data-help="fmea-criteria"]'
        text: Your own scales and rule, set to what your procedure says. Nothing here comes from a standard.
        elsewhere: Open Process FMEA first.
      - target: '[data-help="fmea-rule"]'
        text: An RPN threshold, or a lookup table of S / O / D ranges. A combination the rule does not decide stops approval.
        elsewhere: Open Process FMEA first.
  - id: pfmea
    text: Open **PFMEA-00001**, receiving and kitting M8 bolts.
    to: /quality/fmea
    expect: three rows with S, O, D and the RPN computed (160, 60, 90); the first needs action under the rule and has one; approved by Dana and fixed.
    tour:
      - target: '[data-help="fmea-files"]'
        text: Each PFMEA with its version, status and the nonconformance reports on its item since it was approved.
        elsewhere: Open Process FMEA first.
  - id: draft
    text: Start a new version of PFMEA-00001. If the AI is set up, press *Draft rows*; check each drafted row, give its ranks and confirm it, or remove it.
    to: /quality/fmea
    expect: drafted rows are marked AI and have no ranks; the PFMEA cannot be approved until each is confirmed or removed, and someone who did not edit it approves.
    tour:
      - target: '[data-help="fmea-rows"]'
        text: RPN = S × O × D, computed. A row the AI drafted is highlighted until a person confirms it.
        elsewhere: Open a PFMEA first.
blocks:
  - text: RPN and whether a row needs action are computed from the company's rule; a combination the rule does not decide is not determined and stops approval.
    test: tests/test_fmea.py::test_rules
  - text: A PFMEA is approved, signed, by someone who did not own or edit it; it is then fixed with the criteria used and a fingerprint, and changed only by a new version.
    test: tests/test_fmea.py::test_criteria_approval_and_versions
  - text: The AI drafts rows citing records it was shown and never gives a rank; each drafted row waits for a person.
    test: tests/test_fmea.py::test_ai_drafts_rows_without_ranks
questions:
  - q: How is this different from Risk?
    a: Risk (risk management files) covers product hazards and harm with severity and probability. A process FMEA covers how the process can fail, with severity, occurrence and detection. Both use the company's own scales.
  - q: What happens when a nonconformance report comes in on the item?
    a: The PFMEA lists the reports on its item since it was approved, so a person can decide whether the occurrence of a failure mode needs re-rating. Nothing changes by itself; a new version is how it changes.
  - q: Can we use an action priority table instead of RPN?
    a: Yes. Choose the lookup table and enter your own ranges of S, O and D with a priority for each; say which priorities need action.
---

A *process FMEA* lists, step by step, how a process can fail: the failure mode, its effect, its cause, and the
controls already in place to prevent the cause or detect the failure. Each row gets three ranks on the company's own
scales - severity of the effect, occurrence of the cause, detection by the controls - and WenQuest Ops computes the
RPN, S × O × D. The company's rule says when a row needs action: an RPN threshold, or a lookup table of ranges.

A PFMEA is a controlled document. Someone who did not own or edit it approves it with a signature; it is then kept as
approved, with the criteria used and a fingerprint, and changed only by a new version. A corrective or preventive
action can be opened from a row.

The AI can draft rows from the records about the item - nonconformance reports, inspections, complaints, production
lots, conclusions of cause analyses - citing them. It never gives a rank; a person checks every drafted row, ranks it
and confirms it, or removes it.
