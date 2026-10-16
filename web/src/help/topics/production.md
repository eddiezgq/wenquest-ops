---
title: Production records
group: Regulated modules
order: 5
summary: Templates, lots, steps, materials and release.
needs: quality:view
---

**Production** keeps the record of each lot made (the device history record). The items, lots and work orders are
ERPNext's; WenQuest Ops adds the controlled steps, the signatures and the release. First draft a **template** for an
ERPNext item: its steps (a *check* passed or failed by the operator, a *measurement* with a lower and/or upper limit,
or a *record* of what was done), the controlled documents the steps follow, and the materials each lot must record.
Someone who did not draft or edit it activates it with a password; it is then fixed, and *Start a new version*
copies it into a draft (activating that retires the old version).

*Start a lot* from an active template with the lot or serial number (unique per item) and the quantity planned; the
steps are copied, so a later version does not change a lot already started. Steps are recorded in order, each with
the operator's password. A measurement is judged by WenQuest Ops against the limits, the limits themselves included;
equipment named must be in calibration, and a step can require it. When the template's documents need reading, the
operator must have confirmed reading the revision in effect (*My reading*) first (a setting). A failed step needs a
nonconformance report: *Open a nonconformance* fills it in. Materials are recorded from lots incoming inspection
released, never more than a lot held in all. Submit the record once every step is recorded, the good quantity is
entered and the required materials are recorded; Quality releases or rejects it with a password: someone who recorded
no step or material, with the nonconformance reports closed. If equipment a lot used is later found out of tolerance,
the lot is listed in the assessment and held until the assessment is signed. Released and rejected records are fixed
with a fingerprint; a record is cancelled with a reason while in production; nothing is deleted.
