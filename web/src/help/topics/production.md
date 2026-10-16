---
title: Production records
group: Regulated modules
order: 5
summary: Templates, lots, steps, materials and release.
needs: quality:view
try:
  - id: template
    text: Open *Production* and, under *Templates*, open **KIT-M8**. Read its three steps.
    to: /quality/production
    expect: the status "active", a count check, a box weight measurement from 0.9 to 1.1 kg and a label number record, with BOX-12 as the material each lot records.
    tour:
      - target: '[data-help="production-templates"]'
        text: Each template with its item, version, status and number of steps. Lots start only from an active template.
  - id: released
    text: Set the list of records to *Released* and open the released KIT-M8 lot. Read its steps, materials and the release.
    to: /quality/production
    expect: every step passed with who recorded it, a BOX-12 lot under *Materials*, Dana's signature and a fingerprint.
    tour:
      - target: '[data-help="production-records"]'
        text: One record per lot. Choose Open, Released, Rejected, Cancelled or All above the list.
  - id: record-steps
    text: Sign in as **Sam** (Operations manager). Set the list back to *Open* and open the KIT-M8 lot in production. Record step 2 with a reading of **1.02** and your password, then step 3 with the label serial.
    to: /quality/production
    expect: both steps "pass", with Sam's name and the time.
    tour:
      - target: '[data-help="production-record-step"]'
        text: Only the next step can be recorded, with the operator's password. WenQuest Ops judges a measurement against the limits.
        elsewhere: Open the KIT-M8 lot in production first.
  - id: material
    text: Under *Materials*, choose the released BOX-12 lot and the quantity used (**20**, or what is left if less). Choose *Add*.
    expect: '"Material recorded." and the lot with its supplier in the list.'
    tour:
      - target: '[data-help="production-materials"]'
        text: Only lots that incoming inspection released can be chosen, never more than a lot held in all.
        elsewhere: Open the KIT-M8 lot in production first.
  - id: submit
    text: Enter **20** good and **0** scrapped, choose *Save*, then *Submit for review*.
    expect: the status "qa review".
    tour:
      - target: '[data-help="production-qty"]'
        text: The good and scrapped quantities, together at most the quantity planned.
        elsewhere: Open the KIT-M8 lot in production first.
  - id: release
    text: Sign out, sign in as **Jordan** (Quality), open the lot and choose *Release (sign)* with your password.
    expect: the status "released" and a fingerprint.
    tour:
      - target: '[data-help="production-decide"]'
        text: Quality releases or rejects the lot with a password. Someone who recorded a step or a material in it cannot.
        elsewhere: Open the lot as Jordan first.
blocks:
  - text: Whoever drafted or edited a template cannot activate it; the steps of an active template cannot be changed, not even in the database.
    test: tests/test_production.py::test_templates_are_controlled
  - text: Steps are recorded in order, each with the operator's own password, and a recorded step cannot be changed.
    test: tests/test_production.py::test_lot_from_start_to_release
  - text: Materials come only from lots that incoming inspection released, and never more than a lot held in all.
    test: tests/test_production.py::test_lot_from_start_to_release
  - text: A record is not submitted while a failed step has no nonconformance report, and not released while that report is open.
    test: tests/test_production.py::test_lot_from_start_to_release
  - text: Whoever recorded a step or a material cannot release or reject the lot; rejecting needs a reason.
    test: tests/test_production.py::test_lot_from_start_to_release
  - text: An operator who has not confirmed reading the template's documents, or who names no equipment where a step requires it, cannot record the step; a lot measured with equipment found out of tolerance is held.
    test: tests/test_production.py::test_equipment_and_reading
questions:
  - q: Where do the items and work orders come from?
    a: From ERPNext. WenQuest Ops adds the controlled steps, the signatures and the release.
  - q: Does a new template version change lots already started?
    a: No. The steps are copied when a lot starts, so a later version does not change it.
  - q: A step failed. What now?
    a: Choose *Open a nonconformance* on that step. The record can be submitted once every failed step has a report, and released once those reports are closed.
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
