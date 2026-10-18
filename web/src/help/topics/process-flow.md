---
title: Process flow
group: Quality
order: 10
summary: Draw a production process step by step, with rework loops, and link each step to its documents, PFMEA rows, plans, templates and gauges.
needs: quality:view
try:
  - id: chart
    text: 'Sign in as **Jordan** (Quality). Open *Process flow* and open **PF-00001**, receiving and kitting M8 bolts.'
    to: /quality/flow
    expect: seven steps from the dock to shipping; a dashed rework loop from weighing back to kitting; rejected lots leaving the flow at incoming inspection.
    tour:
      - target: '[data-help="flow-charts"]'
        text: Each process drawn step by step; approved by someone else, then fixed.
        elsewhere: Open Process flow first.
  - id: links
    text: Click the step *Weigh the kit*.
    to: /quality/flow
    expect: its links - the PFMEA row on missing bolts and the torque wrench, marked calibration overdue.
    tour:
      - target: '[data-help="flow-diagram"]'
        text: Click a step to see what it links to. A link to nothing in effect is marked (!) and stops approval.
        elsewhere: Open a flow chart first.
      - target: '[data-help="flow-step"]'
        text: Each link opens the document, PFMEA, plan, template or gauge it points to.
        elsewhere: Open a flow chart and click a step.
  - id: version
    text: Press *Start a new version*, add or move a step, and ask someone who did not edit it to approve.
    to: /quality/flow
    expect: the new version is a draft copy; once approved, the old version is superseded.
    tour:
      - target: '[data-help="flow-approve"]'
        text: Approved with a signature by someone who does not own and did not edit it; what each link pointed to is kept.
        elsewhere: Open a flow chart first.
blocks:
  - text: A branch goes to a step of the chart, or (for scrap and other) out of the flow; a rework branch always goes to a step.
    test: tests/test_flow.py::test_rules
  - text: A step linked to a document not in effect, a PFMEA row with no approved version, or a retired gauge cannot be approved.
    test: tests/test_flow.py::test_flow_chart_on_demo_records
  - text: An approved flow chart is fixed with what its links pointed to; what has moved since is shown.
    test: tests/test_flow.py::test_flow_chart_on_demo_records
questions:
  - q: How does it relate to the PFMEA?
    a: The flow chart is the backbone of the PFMEA. Link each operation and inspection to the PFMEA rows that analyse it; steps with none are listed under the chart, and the PFMEA page lists the flow steps that cite it.
  - q: What does a link point to when a document is revised?
    a: To the revision now in effect. An approved chart keeps the revision it was approved with and shows that a newer one is in effect; whether the process changed is for a person to decide.
---

A *process flow chart* draws how a product is made, step by step: operations, inspections, moves, storage and
waits, in order. Branches show what happens off the main path - a light kit sent back to be counted again, a rejected
lot returned to the supplier.

Each step can link to what it rests on: the controlled documents people follow, the PFMEA rows that analyse it, the
incoming inspection plan, the production template and the measuring equipment. Links are checked against what is in
effect; a link to nothing in effect stops approval.

A flow chart is a controlled document. Someone who did not own or edit it approves it with a signature; it is then
kept as approved, with what each link pointed to and a fingerprint, and changed only by a new version.
