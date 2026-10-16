---
title: Supplier quality and control charts
group: Quality
order: 5
summary: Facts per supplier and control charts of your measurements.
needs: quality:view
try:
  - id: suppliers
    text: Sign in as **Jordan** (Quality). Open *Quality* and choose the *Supplier quality* tab.
    to: /quality?tab=suppliers
    expect: the last 90 days per supplier. Gulf Fasteners (Demo) has a rejected lot, a nonconformance report and, until CAPA-00001 is closed, an open corrective action.
    tour:
      - target: '[data-help="supplier-scores"]'
        text: Facts only, counted from ERPNext and the quality records. No made-up score.
  - id: unknown
    text: Look at **Coastal Packaging (Demo)**. None of its lots were inspected in ERPNext in the period.
    expect: its rejection rate shows "unknown", not 0%.
  - id: chart
    text: Choose the *SPC* tab and pick **HX-BOLT-M8** with its pitch diameter.
    to: /quality?tab=spc
    expect: a chart of the readings of each inspection, with points marked where they break a rule as the diameter creeps upwards.
    tour:
      - target: '[data-help="spc-pick"]'
        text: Every item and parameter with numeric readings on ERPNext inspections, with how many inspections there are.
        elsewhere: Choose the SPC tab first.
      - target: '[data-help="spc-chart"]'
        text: Center line, control limits and spec limits. Marked points break a Western Electric rule.
  - id: signals
    text: Read the *Signals* and *Capability* boxes under the chart.
    expect: each broken rule with its point, and Cp, Cpk, Pp and Ppk with the number of values and how many are out of spec.
    tour:
      - target: '[data-help="spc-signals"]'
        text: Each point that breaks a rule, and which rule.
        elsewhere: Choose the SPC tab and an item first.
      - target: '[data-help="spc-capability"]'
        text: Shown only when the readings have both spec limits.
blocks:
  - text: No supplier gets a score or grade. A supplier with no inspected lots has an unknown rejection rate, not 0.
    test: tests/test_quality_data.py::test_supplier_facts
  - text: A control chart is not drawn from too little data.
    test: tests/test_quality_data.py::test_individuals_and_rules
  - text: People without access to quality records cannot see supplier quality.
    test: tests/test_quality_data.py::test_quality_data_api
questions:
  - q: Which lots count?
    a: Incoming quality inspections submitted in ERPNext for purchase receipts, in the last 90 days. An inspection still waiting on the Drafts page does not count yet.
  - q: Why individuals and not X-bar and R?
    a: X-bar and R needs every inspection to have the same number of readings, 2 to 10. Otherwise the chart shows individual values.
  - q: What is a concession here?
    a: A closed nonconformance report whose disposition needed approval, such as use as is.
---

*Quality* in the sidebar, tab *Supplier quality*: facts per supplier over the last 90 days. Lots inspected and
rejected, rejection rate, on-time rate, NCRs, concessions and open corrective actions. No made-up score.

## Control charts (SPC)

![Control chart of a drifting parameter](img/quality-spc.webp)

*Quality*, tab *SPC*: numeric readings on ERPNext inspections become control charts per item and parameter: X-bar
and R when every inspection has the same number of readings (2–10), otherwise individuals. Points that break a
Western Electric rule are marked. With spec limits you also get Cp, Cpk, Pp and Ppk.
