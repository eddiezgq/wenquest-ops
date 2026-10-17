---
title: Device labels and scanning
group: Regulated modules
order: 6
summary: Record each item's device identifier, print the label of a released lot, and scan codes to find their records.
needs: quality:view
try:
  - id: identifier
    text: 'Sign in as **Jordan** (Quality manager). Open *Production*, then *Device identifiers*. To add one, choose an item, GS1 or HIBCC, type what your agency gave you and save.'
    to: /quality/udi
    demo: /quality/udi
    expect: 'in the demo, HX-BOLT-M8 with the GTIN 09521234567899 (GS1 keeps the prefix 952 for examples); its history says who set it. A wrong check digit is refused.'
    tour:
      - target: '[data-help="udi-form"]'
        text: The identifier your issuing agency gave the item. A wrong check digit is refused; nothing is made up.
        elsewhere: Only the quality team can set identifiers.
      - target: '[data-help="udi-list"]'
        text: Every item with an identifier, and who set or changed it.
  - id: label
    text: Open a released lot of that item (in the demo, DHR-00001 of HX-BOLT-M8) and look at *Device label*. Enter an expiry date and print, or download the ZPL file for a label printer.
    demo: /quality/production/1
    expect: 'a GS1 DataMatrix and the text (01)09521234567899(11)…(17)…(10)<lot>.'
    tour:
      - target: '[data-help="production-label"]'
        text: The label of a released lot. Each print is recorded with who printed it and how many.
        elsewhere: Open a released production lot first.
  - id: scan
    text: Open *Scan* and type or scan the text of the label.
    to: /scan
    expect: the identifier, lot and dates read out, with links to the item, the lot and its trace.
    tour:
      - target: '[data-help="scan-box"]'
        text: A barcode scanner types here. On a phone or tablet, use the camera.
blocks:
  - text: A GTIN with a wrong check digit, or one already given to another item, is refused.
    test: tests/test_udi.py::test_labels_and_scans
  - text: Labels are printed only for released lots, and the expiry cannot be before the production date.
    test: tests/test_udi.py::test_labels_and_scans
  - text: Every change of an identifier and every label print is kept and cannot be deleted.
    test: tests/test_udi.py::test_labels_and_scans
  - text: Anyone can read a code; only the quality team sees the records it matches.
    test: tests/test_udi.py::test_udi_api
questions:
  - q: Where do I get a device identifier?
    a: From an issuing agency the FDA accredited, such as GS1 (a GTIN) or HIBCC (a labeler code; its free UDI Builder makes HIBC labels). WenQuest Ops checks it but never issues one.
  - q: Does this send anything to the FDA?
    a: No. Submitting the device to the FDA's GUDID is done in GUDID itself.
  - q: Which scanners work?
    a: Any USB or Bluetooth scanner that types what it reads, and the camera of a phone or tablet in the browser. GS1 DataMatrix, GS1-128, HIBC codes, GS1 web addresses and the GTIN of a box are read. Set the scanner to send the GS separator of GS1 codes (most send it as Ctrl+], which the Scan box writes as <GS>); without it a lot followed by a serial number cannot be told apart.
---

A medical device carries a unique device identification (UDI): the device identifier (DI) of the model, and the
production identifiers of the unit, such as the lot, serial number and dates. Record the DI of each item in
*Device identifiers*. A released lot then shows its label, ready to print on paper or on a label printer.

*Scan* reads a code from a label, a box or a supplier's delivery, and finds the item and the production or incoming
lots it belongs to, with a link to trace them.
