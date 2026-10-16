---
title: Signatures and workflows
group: Quality
order: 6
summary: How signing works and how a company tightens its workflows.
needs: quality:view
---

Signing means re-entering **your own WenQuest Ops password**. If you sign in with Microsoft or Google, set a password
first. Signatures and the quality history can never be changed or deleted.

## Workflows

*Quality → Workflows* shows how nonconformance reports and corrective actions move: their states in order and, for
every step, who may do it, what it needs, whether it is signed and who may not do it (for example, the person who
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
