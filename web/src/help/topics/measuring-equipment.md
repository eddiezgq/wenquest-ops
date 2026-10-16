---
title: Measuring equipment
group: Regulated modules
order: 2
summary: Gauges, calibrations, and what a failed calibration affects.
video: measuring-equipment
needs: quality:view
try:
  - id: list
    text: Open *Measuring equipment*. Find **TW-02**, the torque wrench, whose next due date has passed.
    to: /quality/gauges
    expect: CAL-01 and CAL-02 in service; TW-02 with its due date in red and "(overdue)".
    tour:
      - target: '[data-help="gauges-list"]'
        text: Each piece of equipment with its status, its last good calibration and when the next one is due.
  - id: overdue
    demo: /quality/gauges/3
    text: Open **TW-02**.
    expect: '"Cannot be used: TW-02 was due for calibration on" and the date.'
    tour:
      - target: '[data-help="gauge-usable"]'
        text: Whether the equipment can be used today, and why not.
        elsewhere: Open TW-02 from the list first.
  - id: record
    demo: /quality/gauges/3
    text: Sign in as **Jordan** (Quality). On TW-02, record a calibration with today's date, by **Bay Calibration Lab (Demo)**, result *pass*. Choose *Record*.
    expect: '"Calibration recorded: someone else approves it." and a new row "recorded by" Jordan.'
    tour:
      - target: '[data-help="gauge-record"]'
        text: The date, who calibrated it, the certificate, pass or out of tolerance, as found and as left.
        elsewhere: Open TW-02 first.
  - id: approve
    demo: /quality/gauges/3
    text: Sign out and sign in as **Dana** (Owner). Open TW-02 and approve the new calibration with your password.
    expect: the status "in service", "Can be used" and a next due date six months after today.
    tour:
      - target: '[data-help="gauge-calibrations"]'
        text: Someone other than whoever recorded or last changed the calibration approves it, with a password.
        elsewhere: Open TW-02 first.
  - id: fail
    text: As **Jordan**, open **CAL-01** and record a calibration dated yesterday with the result *fail (out of tolerance)* and what was found. As **Dana**, approve it.
    expect: CAL-01 "out of service" and a red box listing the incoming inspections it measured since its last good calibration.
    tour:
      - target: '[data-help="gauge-impact"]'
        text: What the equipment measured since its last good calibration. Quality decides whether those results still stand.
        elsewhere: Open CAL-01 after the failed calibration is approved.
  - id: assess
    text: As **Jordan**, write whether those results still stand, tick *open a nonconformance report* if needed, and choose *Sign the assessment*.
    expect: the assessment under *Out-of-tolerance assessments*; CAL-01 is still out of service.
  - id: back
    text: Record a good calibration of CAL-01 dated today, and have **Dana** approve it.
    expect: CAL-01 back "in service".
blocks:
  - text: Whoever recorded a calibration, or last changed it, cannot approve it.
    test: tests/test_calibration.py::test_calibration_approved_by_someone_else
  - text: A good calibration older than the last approved one is refused, and an approved calibration cannot be changed, not even in the database.
    test: tests/test_calibration.py::test_calibration_approved_by_someone_else
  - text: Out-of-tolerance equipment stays out of service until the assessment is signed and a good calibration after the failure is approved; its status cannot be set by hand.
    test: tests/test_calibration.py::test_out_of_tolerance
  - text: The assessment needs a written conclusion; once signed it cannot be changed.
    test: tests/test_calibration.py::test_out_of_tolerance
  - text: An inspector cannot sign an incoming inspection measured with equipment that is out of service or past its due date on that day.
    test: tests/test_calibration.py::test_inspection_names_equipment_in_calibration
  - text: Equipment named on an inspection is checked even when naming it is switched off.
    test: tests/test_calibration.py::test_named_equipment_is_checked_even_when_not_required
questions:
  - q: Why is new equipment out of service?
    a: It stays out of service until its first good calibration is approved.
  - q: Why can I not approve a calibration I recorded?
    a: Someone other than whoever recorded or last changed it approves it, with a password.
  - q: What happens to production lots measured with equipment found out of tolerance?
    a: They are listed in the assessment and held until it is signed.
---

**Measuring equipment** lists the company's gauges and instruments with how often each is calibrated. New equipment is
out of service until its first good calibration is approved. Record each calibration (date, who did it, the
certificate, pass or out of tolerance, as found and as left); someone other than whoever recorded or last changed it
approves it with a password. A good calibration sets the next due date; an older one than the last good calibration
cannot be approved.

When a calibration finds the equipment out of tolerance, approving it takes the equipment out of service and lists
the incoming inspections it measured since its last good calibration. Quality writes whether those results still
stand and signs (a nonconformance report can be opened at the same time). The equipment returns to service once that
assessment is signed and a good calibration after the failure is approved.

Once any equipment is registered, an incoming inspection names the equipment used for each measured characteristic,
and the inspector can only sign if that equipment is in service and not past its due date on that day; what was used,
and when it was due, stays with the inspection. This can be switched off under *Incoming inspection → Inspection
levels → Who may do what*. The ISO calibration check reads this list as well as the calibration register.
