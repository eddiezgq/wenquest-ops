---
title: Corrective and preventive actions
group: Quality
order: 2
summary: Find the cause, plan the actions, check they worked.
video: corrective-actions
needs: quality:view
try:
  - id: open-list
    text: Sign in as **Jordan** (Quality). Open *Quality* and choose the *Corrective actions* tab.
    to: /quality?tab=capas
    expect: CAPA-00001, "Supplier thread rolling out of tolerance", in implementation.
    tour:
      - target: '[data-help="quality-tabs"]'
        text: Choose *Corrective actions* here.
      - target: '[data-help="quality-list"]'
        text: The open corrective and preventive actions, with their kind, status and owner.
  - id: read
    demo: /quality/capa/1
    text: Open **CAPA-00001**. Read the root cause and the action given to **Pat**.
    expect: the stage "implementation" highlighted, a link to NCR-00001, and the action "Supplier to send 8D and first-article data" marked overdue.
    tour:
      - target: '[data-help="capa-stages"]'
        text: Draft, investigation, implementation, effectiveness check, closed. The current stage is dark.
        elsewhere: Open CAPA-00001 first (Quality, Corrective actions).
      - target: '[data-help="capa-actions"]'
        text: Each action with its owner and due date. An action past its date is marked overdue.
  - id: too-early
    demo: /quality/capa/1
    text: Choose *All actions done — check effectiveness*.
    expect: '"actions not done yet: Supplier to send 8D and first-article data". The stage does not change.'
    tour:
      - target: '[data-help="capa-next-step"]'
        text: The fields of this stage, and the button that moves the action on when they are filled in.
        elsewhere: Open CAPA-00001 first.
  - id: owner-done
    text: Sign out and sign in as **Pat** (Purchasing). Open CAPA-00001, write the evidence (for example **8D and first-article report received**) next to the action and choose *Done*.
    expect: a tick, Pat's name and the evidence. Pat does not work in Quality but owns the action.
  - id: check
    text: Sign in as **Jordan** again, open CAPA-00001 and choose *All actions done — check effectiveness*.
    expect: the stage "effectiveness" and an *Effectiveness check* box.
  - id: close
    text: Write the evidence for the check (for example **Next 3 bolt lots accepted**), enter your password and choose *Effective — close (sign)*.
    expect: the stage "closed" and a signature by Jordan. Pat owns the action, so Pat could not have closed it.
    tour:
      - target: '[data-help="capa-effectiveness"]'
        text: Effective closes it, signed by someone other than the owner. Not effective sends it back to implementation with the reason.
        elsewhere: Move CAPA-00001 to the effectiveness check first.
  - id: close-ncr
    text: Open **NCR-00001** and close it with a note and your password.
    to: /quality?tab=ncrs
    expect: the status "closed". A major report closes once its corrective action is closed.
blocks:
  - text: The investigation does not start without a problem description and a risk level; implementation does not start without containment, root cause and at least one action.
    test: tests/test_quality.py::test_capa_stages
  - text: An action's due date cannot be in the past. Only the action's owner or Quality marks it done, and only with the evidence.
    test: tests/test_quality.py::test_capa_stages
  - text: The effectiveness check does not start while actions are still open.
    test: tests/test_quality.py::test_capa_stages
  - text: The owner cannot close their own corrective action as effective.
    test: tests/test_workflow.py::test_messages_and_order_as_in_phase_one
  - text: A nonconformance report has only one open corrective action at a time.
    test: tests/test_quality.py::test_capa_stages
  - text: Cancelling a corrective action needs a reason.
    test: tests/test_quality.py::test_capa_cancel_and_multiple_ncrs
questions:
  - q: Can one corrective action cover several reports?
    a: Yes. It can be linked to several nonconformance reports, as long as none of them already has another open corrective action.
  - q: What happens when the check finds it was not effective?
    a: Choose *Not effective — back to implementation* with the evidence. It goes back to implementation; add actions and check again.
  - q: Someone outside Quality owns an action. Can they mark it done?
    a: Yes. The owner of an action marks it done with the evidence during investigation or implementation, even without the right to edit quality records.
---

Open one from a nonconformance report with *Open corrective action*. All of them are on *Quality*, tab
*Corrective actions*.

**Draft → Investigation → Implementation → Effectiveness check → Closed.**

- To start the investigation: problem description, owner and risk level.
- To implement: containment, root cause and at least one action.
- Actions have an owner and a due date; the owner marks them done with evidence, even outside Quality.
- Effectiveness check: *effective* closes it, signed by someone **other than the owner**; *not effective* sends it
  back to implementation with the reason.
