---
title: Incoming inspection
group: Quality
order: 3
summary: Sampling table, inspection plans, inspecting a lot and deciding.
needs: quality:view
---

Items marked *inspection required before purchase* in ERPNext appear under **Incoming inspection** when received.
Draft an inspection with your sample size; Quality confirms it on the Drafts page; enter the readings in ERPNext.

To inspect by plan and sampling table instead, use **Incoming inspection** in the sidebar:

- **Sampling table**: the owner or Quality enters the rows of the company's sampling table (AQL, inspection level,
  lot size range, sample size n and acceptance number Ac; Re is Ac + 1) from the company's own controlled copy of the
  standard it uses. WenQuest Ops does not supply these numbers. Mark a row as checked, naming the source, once someone
  has compared it with that copy. A row an inspection used cannot change: archive it and add a new one.
- **Plans**: a plan for an item gives its AQL and the characteristics to check: measured ones with a lower and/or upper
  limit, or pass/fail ones. A plan is enabled with a password by someone other than the person who drafted it, and is
  then frozen; a change is a new version.
- **Inspections**: start one from a waiting receipt line (or for a lot not on a receipt). The sampling table gives n,
  Ac and Re for the lot size and the supplier's inspection level; a lot smaller than the sample is inspected piece by
  piece. Enter the readings and sign: the lot is judged by code (a sample unit fails if any reading fails; the lot is
  accepted with Ac or fewer failing units). Someone other than the inspector then releases or rejects the lot with a
  password. The result goes to Drafts as an ERPNext quality inspection to confirm; a rejected lot gets a
  nonconformance report, which is linked to that inspection once it is submitted in ERPNext. A lot sampled with a row
  not yet checked is flagged, and releasing it needs a reason.
- **Inspection levels**: the switching rules suggest moving a supplier's item between normal, tightened and reduced
  inspection from the lots decided at its current level. A person switches, with a reason. The starting rules are
  defaults: set them to what your procedure says. Who may do what (the "someone other" rules) can be switched off
  there too.
