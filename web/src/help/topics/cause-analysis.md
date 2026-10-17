---
title: Cause analysis
group: Quality
order: 8
summary: Fishbone diagrams and 5 Why on a nonconformance report, a corrective action or a complaint, with AI suggestions that cite your records.
needs: quality:view
try:
  - id: fishbone
    text: 'Sign in as **Jordan** (Quality). Open *Quality tools*, tab *Cause analysis*, and open **RCA-00001**, the fishbone on the rejected HX-BOLT-M8 lot.'
    to: /quality/tools?tab=causes
    expect: the causes on their bones, each with the records it rests on; the root cause is signed and written to D4 of the report's 8D.
    tour:
      - target: '[data-help="causes-list"]'
        text: Every analysis, with the record it is on. Start one from the nonconformance report, corrective action or complaint.
        elsewhere: Open the Cause analysis tab of Quality tools first.
  - id: why
    text: Open **RCA-00002**, the 5 Why on the complaint about stripped M8 bolts. Answer why 3 yourself, or press *Suggest answers to why 3* if the AI is set up.
    to: /quality/tools?tab=causes
    expect: each why rests on the answer above it; the AI's suggestions are dashed until you accept, edit or remove them.
    tour:
      - target: '[data-help="cause-whys"]'
        text: One confirmed answer per why. The next why opens only after a person accepts an answer to this one.
        elsewhere: Open a 5 Why first.
      - target: '[data-help="cause-suggest"]'
        text: The AI reads the records listed under *Records the AI reads* and must cite them. Anything citing no record it was shown is dropped.
        elsewhere: Open an analysis that is still open.
  - id: conclude
    text: When every suggestion is decided, write the root cause, type your password and press *Conclude and sign*.
    to: /quality/tools?tab=causes
    expect: the record's root cause now ends with your conclusion and the analysis number; the analysis can no longer change, only take addenda.
    tour:
      - target: '[data-help="cause-conclude"]'
        text: Signed with your password and added to the record's root cause; what was there stays.
        elsewhere: Open an analysis that is still open.
blocks:
  - text: A suggestion of the AI that cites no record it was shown is dropped, and the run records what was dropped.
    test: tests/test_cause_analysis.py::test_fishbone_on_a_report
  - text: Every AI suggestion is accepted, edited or removed by a person before the analysis can be concluded.
    test: tests/test_cause_analysis.py::test_fishbone_on_a_report
  - text: A why opens only after an answer to the why above is accepted, and an answer others rest on cannot be removed first.
    test: tests/test_cause_analysis.py::test_five_why_on_a_complaint_and_a_capa
  - text: Once concluded, an analysis is never changed; later findings are added as addenda.
    test: tests/test_cause_analysis.py::test_fishbone_on_a_report
questions:
  - q: What does the AI read?
    a: The record analysed and related ones - other reports, incoming inspections, complaints and production lots of the same item or supplier, the measuring equipment used on the item, recent changes and earlier conclusions. Open *Records the AI reads* to see the list.
  - q: Can we use our own categories instead of the six usual ones?
    a: Yes, when the fishbone is started through the API; on the page it starts with People, Machines, Materials, Methods, Environment and Measurement.
  - q: Do we need the AI?
    a: No. Without a model key, people add every cause themselves; everything else works the same.
---

A *fishbone* sorts possible causes of one problem into categories - people, machines, materials, methods,
environment, measurement. A *5 Why* asks why the problem happened, then why that happened, until it reaches something
the company can change. Both hang on the record they analyse: a nonconformance report, a corrective action or a
complaint. Start one from the bottom of that record's page.

Each cause can name the records it rests on, such as an incoming inspection or an earlier report, and those numbers
are checked. The AI can suggest causes from the same records; it must cite them, and suggestions that cite records it
was not shown are dropped. A suggestion stays dashed until a person accepts, edits or removes it.

The conclusion is signed with your password and added to the record's root cause: section D4 of a report's 8D, or the
root cause of the corrective action or complaint. After that the analysis is kept exactly as it was.
