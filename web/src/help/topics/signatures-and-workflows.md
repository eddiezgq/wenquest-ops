---
title: Signatures and workflows
group: Quality
order: 6
summary: How signing works and how a company tightens its workflows.
needs: quality:view
try:
  - id: password
    text: Sign in as **Jordan** (Quality) and open *My account*.
    to: /account
    expect: a box to change your password. This is the password you sign with.
    tour:
      - target: '[data-help="account-password"]'
        text: You sign quality records with this password. People who sign in with Microsoft or Google set one here first.
  - id: workflows
    text: Open *Quality* and choose the *Workflows* tab.
    to: /quality?tab=workflows
    expect: the nonconformance report and the corrective action workflows, each with "version 1 in use", their states in order and every step.
    tour:
      - target: '[data-help="workflow-card"]'
        text: For each step, where it starts and ends, what it needs, whether it is signed, who may not do it and who may.
        elsewhere: Choose the Workflows tab first.
  - id: draft
    demo: /quality?tab=workflows
    text: Under the nonconformance report, choose *Change this workflow*.
    expect: a draft page, "Nonconformance report workflow · version 2".
    tour:
      - target: '[data-help="workflow-change"]'
        text: Makes a draft copy of the version in use. Only the owner and Quality see this button.
        elsewhere: Choose the Workflows tab first.
  - id: edit
    text: Under *Steps*, rename the step **Contain** to **Quarantine**, and change what the close signature means to **NCR closed by Quality**. Choose *Save draft*.
    expect: '"Saved. Someone who did not change it enables it." Both changes are listed under the changes from version 1, and the check says it keeps every rule that cannot be switched off.'
    tour:
      - target: '[data-help="workflow-steps"]'
        text: Rename steps, word the signatures, add what a step needs, keep more people from it, limit it to some roles.
        elsewhere: Open the draft first.
      - target: '[data-help="workflow-changes"]'
        text: Every change from the version in use.
      - target: '[data-help="workflow-check"]'
        text: The rules that cannot be switched off, checked on every save.
  - id: not-own
    text: Look at the *Enable* box at the bottom.
    expect: '"You changed this draft, so someone else with the right to change workflows enables it."'
    tour:
      - target: '[data-help="workflow-enable"]'
        text: Whoever changed the draft cannot enable it.
        elsewhere: Open the draft first.
  - id: enable
    text: Sign out and sign in as **Dana** (Owner). Open *Quality*, *Workflows*, choose *Open the draft (version 2)*, enter your password and choose *Enable (sign)*.
    to: /quality?tab=workflows
    expect: '"Enabled. New records follow this version." and the signature "Workflow version enabled".'
    tour:
      - target: '[data-help="workflow-open-draft"]'
        text: Opens the draft someone else changed.
        elsewhere: Choose the Workflows tab first.
  - id: kept
    text: Go back to the *Workflows* tab.
    to: /quality?tab=workflows
    expect: '"version 2 in use" with the step Quarantine. Reports opened before, such as NCR-00001, keep version 1.'
blocks:
  - text: A wrong password signs nothing and changes nothing.
    test: tests/test_quality.py::test_ncr_without_approval
  - text: People who sign in only with Microsoft or Google cannot sign until they set a WenQuest Ops password.
    test: tests/test_quality.py::test_sso_only_people_need_a_password_to_sign
  - text: Signatures and the quality history cannot be changed or deleted, not even in the database.
    test: tests/test_quality.py::test_logs_and_signatures_cannot_be_changed
  - text: No workflow version can drop a signature, approval by someone else, a step or state WenQuest Ops needs, or the rule that a major report closes only after its corrective action.
    test: tests/test_workflow.py::test_red_lines_cannot_be_configured_away
  - text: A draft is enabled only by someone who did not change it, with their password, and only when its check passes. An enabled version cannot change.
    test: tests/test_workflow_admin.py::test_draft_change_and_signed_enabling
  - text: A suggestion from a procedure is accepted only when its quote was found in that procedure.
    test: tests/test_workflow_proposals.py::test_proposal_is_checked_kept_and_decided
questions:
  - q: Who can change a workflow?
    a: The owner and Quality. Someone who did not change the draft enables it.
  - q: What happens to open reports when a new version is enabled?
    a: They keep the version they were opened under, shown at the top of their page. New reports and actions follow the new version.
  - q: Can the AI change a workflow?
    a: No. With the company's model key it can suggest changes from your procedures in effect, each with a quote. A person accepts or rejects each one, and someone who did not change the draft enables it.
---

Signing means re-entering **your own WenQuest Ops password**. If you sign in with Microsoft or Google, set a password
first on *My account*. Signatures and the quality history can never be changed or deleted.

## Workflows

*Quality*, tab *Workflows*, shows how nonconformance reports and corrective actions move: their states in order and,
for every step, who may do it, what it needs, whether it is signed and who may not do it (for example, the person who
submitted a disposition cannot approve it). These rules are a configuration that WenQuest Ops checks before every
step; each report and action keeps the version it was opened under, shown at the top of its page. Signing,
approval by someone else and the record history cannot be switched off by any configuration.

**Changing a workflow.** People with the right to change workflows (the owner and Quality) choose *Change this
workflow*. The new version starts as a draft copy of the one in use. You can rename states and steps, word the
signatures, add what a step needs, keep more people from a step, limit a step to some roles, add your own fields
(for example a lot number, needed before containment), add extra signed approvals (for example "the owner approves
closing a major report") and tighten the rules. The page shows every change from the version in use and checks the
rules that cannot be switched off. Someone who did not change the draft enables it with their password; reports and
actions opened before keep their version.

**Suggestions from your procedures.** With the company's model key, the same people can let the AI read the
procedures in effect in the document library (approved there; those about nonconformances or corrective actions are
ticked first) and suggest changes to the workflow, for example "QP-08 asks for the lot number before the disposition". Every
suggestion quotes the procedure. WenQuest Ops checks that the quote is really in that procedure and that the change
keeps the rules that cannot be switched off. A suggestion can only tighten the workflow: it cannot let more roles do a
step, nor make a step need something no one can fill in by then. Suggestions that fail, or that the workflow already
does, cannot be accepted. You accept or reject each one. Accepted ones go into the draft (a new one is made when there is none), and
someone who did not change the draft enables it with their password, as above. The AI never changes the workflow
itself. What a procedure asks that a workflow cannot do is listed separately, for a person to handle.

![Suggested changes, each with its quote from the procedure](img/workflow-suggestions.webp)
