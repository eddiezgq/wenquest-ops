---
title: Measurement data
group: Quality
order: 4
summary: Readings from gauges and measuring machines, and control charts of your own inspections and lots.
video: measurement-data
needs: quality:view
try:
  - id: chart
    text: 'Sign in as **Jordan** (Quality). Open *Quality*, the *SPC* tab, and pick **BOX-12 — Board thickness (incoming inspections)**.'
    to: /quality?tab=spc
    expect: a control chart of the signed BOX-12 inspections, one point per inspection, with Cp and Cpk marked as a rough guide while there are few values.
    tour:
      - target: '[data-help="spc-pick"]'
        text: Items and characteristics from your incoming inspections, production lots and ERPNext inspections.
        elsewhere: Choose the SPC tab first.
      - target: '[data-help="spc-capability"]'
        text: Computed by code from the plan's limits. Without both limits it says unknown.
  - id: gauge
    text: Open an incoming inspection in progress whose plan has a measured characteristic (in the demo, IQC-00005 of BOX-12). Click the first empty reading and measure with a gauge that types its reading (or type a number and press Enter).
    demo: /quality/iqc/5
    expect: the cursor moves to the next sample of the same characteristic, so you can measure every sample in turn.
  - id: file
    text: 'On the same inspection, under *Measurement file*, choose a CSV file whose first line names the part and the characteristic, such as `Sample,Board thickness` with a line per part (`1,4.02`, `2,3.98`).'
    demo: /quality/iqc/5
    expect: 'the preview matches the column to the characteristic, puts the parts on the first samples with no reading, and writes nothing yet. In the demo, samples 1-4 came from box12-cmm-export.csv, listed under the file box.'
    tour:
      - target: '[data-help="iqc-import"]'
        text: CSV from a measuring machine, or a Q-DAS file. Nothing is written until you sign.
        elsewhere: Open an incoming inspection in progress first.
  - id: sign
    text: Name the equipment it was measured with, type your password and import.
    expect: the readings in the table with a file mark; the file is kept and can be downloaded from the inspection.
blocks:
  - text: A feature of the file goes to a characteristic only when the names match or you choose it; the plan's limits decide, not the file's.
    test: tests/test_measurements.py::test_matching_and_placing
  - text: A value the file cannot give as a number, or one the measuring program marked, is not imported, and is listed.
    test: tests/test_measurements.py::test_reading_files
  - text: An import is signed; a file changed after the preview, or imported before, is refused; equipment out of calibration is refused.
    test: tests/test_measurements.py::test_import_into_an_inspection
  - text: Capability without both limits, or without spread, is unknown, never a pass.
    test: tests/test_measurements.py::test_control_charts_of_the_hubs_readings
questions:
  - q: Which gauges and machines work?
    a: Gauges that send their reading as typed text (most USB calipers, micrometers and indicators with a USB cable), and any coordinate measuring machine, 3D scanner or gauge software that exports CSV or Q-DAS (.dfq). For PDF reports, export CSV from the measuring software.
  - q: What CSV shapes are read?
    a: One row per measured feature (part, feature, axis, nominal, measured, tolerances, as PC-DMIS and Calypso export) or one row per part with a column per characteristic.
  - q: Where do production measurements come from?
    a: From the measure steps of production lots, recorded by the operator. They show on the same charts, one value per lot.
---

Measurements reach an inspection in three ways: typed, sent by a gauge that types its reading, or imported from the
file a measuring machine exported. Every reading names who entered it; one from a file also names the file, which is
kept unchanged with the inspection.

The *SPC* tab draws control charts from signed incoming inspections (one subgroup per inspection), production lots
(one value per lot) and ERPNext quality inspections. Limits, rules and capability are computed by code. A broken rule
is a reason to look: *Open a nonconformance report* starts one with the chart's signals in it.
