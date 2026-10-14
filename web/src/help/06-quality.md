# Quality

## Nonconformance reports (NCR)

![A nonconformance report](img/quality-ncr.webp)

A rejected inspection opens a report automatically; you can also open one by hand.

1. **Contain** — what was done so bad parts go no further (for example, moved to QC Hold).
2. **Disposition** — return to supplier, rework / sort, scrap, or use as is (concession), with quantity and reason.
   Types that need approval (such as *use as is*) must be approved by **someone else**, with their password.
3. **Close** — signed with your password. A *major* report closes only after its corrective action is closed.

Reports can be cancelled with a reason. Nothing is deleted.

## 8D

Write the eight sections on the report. *Mark 8D complete* signs it; after that it cannot change.

## Corrective and preventive actions (CAPA)

**Draft → Investigation → Implementation → Effectiveness check → Closed.**

- To start the investigation: problem description, owner and risk level.
- To implement: containment, root cause and at least one action.
- Actions have an owner and a due date; the owner marks them done with evidence — even outside Quality.
- Effectiveness check: *effective* closes it, signed by someone **other than the owner**; *not effective* sends it
  back to implementation with the reason.

## Incoming inspection

Items marked *inspection required before purchase* in ERPNext appear under **Incoming inspection** when received.
Draft an inspection with your sample size; Quality confirms it on the Drafts page; enter the readings in ERPNext.

## Supplier quality

Facts per supplier: lots inspected and rejected, rejection rate, on-time rate, NCRs, concessions and open
corrective actions. No made-up score.

## Control charts (SPC)

![Control chart of a drifting parameter](img/quality-spc.webp)

Numeric readings on ERPNext inspections become control charts per item and parameter: X-bar and R when every
inspection has the same number of readings (2–10), otherwise individuals. Points that break a Western Electric rule
are marked. With spec limits you also get Cp, Cpk, Pp and Ppk.

## Signatures

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
