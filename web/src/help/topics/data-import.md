---
title: Import from another system
group: Documents
order: 4
summary: Bring items, customers, suppliers, opening stock and open orders from your old system into ERPNext.
needs: data:import
try:
  - id: file
    text: 'On your computer, save a small CSV file named **products.csv** with these lines: `Product/Service Name,Sales Description,Type,Sales Price / Rate` then `TEST-1,Test product,Inventory,9.50` then `HX-BOLT-M8,Bolt,Inventory,11.90`.'
    expect: a file like a QuickBooks products export.
  - id: upload
    text: Sign in as **Dana** (Owner) or **Sam** (Operations manager). Open *Documents* and drop the file in.
    to: /documents
    tour:
      - target: '[data-help="docs-drop"]'
        text: Drop the export here. It is kept in the library like any other file.
  - id: kind
    text: Open the file and, under *Import as a ledger*, choose **Items (into ERPNext)** and start.
    expect: the columns matched to ERPNext's fields, Product/Service Name as the item code, Type as Stock item.
    tour:
      - target: '[data-help="doc-ledger"]'
        text: Choose what the file holds. With an AI key, AI suggests it; without one, the column names decide.
        elsewhere: Open the file you uploaded first.
  - id: preview
    text: Read the rows.
    expect: 'TEST-1 ready to import, and HX-BOLT-M8 "already in ERPNext as HX-BOLT-M8: skipped".'
    tour:
      - target: '[data-help="ledger-rows"]'
        text: Every row with what will happen to it. Nothing has been written yet.
        elsewhere: Start the import of your file first.
  - id: sign
    text: Type your password and choose *Import 1 rows (sign)*.
    expect: '"Into ERPNext: 1 created"; TEST-1 links to its page once WenQuest Ops has read it back.'
    tour:
      - target: '[data-help="ledger-import"]'
        text: Signed with your password. Items, customers and suppliers are created; opening stock and orders become drafts in ERPNext unless you tick the box.
        elsewhere: Start the import of your file first.
  - id: again
    text: Start an import of the same file again and look at the rows.
    expect: both rows skipped now. Nothing is ever doubled.
blocks:
  - text: A record already in ERPNext, or twice in the file, is skipped rather than doubled.
    test: tests/test_erp_import.py::test_items_then_stock_then_orders
  - text: Opening stock or an order that names an item, warehouse or customer ERPNext does not have yet waits until it is imported.
    test: tests/test_erp_import.py::test_items_then_stock_then_orders
  - text: If one line of an order cannot come in, none of the order does.
    test: tests/test_erp_import.py::test_refused_rows_and_a_part_of_an_order
  - text: Only the owner and the operations manager can import into ERPNext, and only with their password.
    test: tests/test_erp_import.py::test_erp_import_api
questions:
  - q: Which systems can I import from?
    a: Any that saves Excel or CSV. The usual column names of QuickBooks, NetSuite, SAP Business One and Odoo exports are recognised; for others, check the mapping or let AI suggest it.
  - q: In what order should I import?
    a: Items, customers and suppliers first, then opening stock, then open sales and purchase orders. Later files need what the earlier ones created.
  - q: Why are my orders drafts?
    a: So someone checks them in ERPNext before they count. Tick the box when signing to submit them at once instead.
---

Moving to ERPNext means bringing the records of your old system with you. Export them from the old system as Excel
or CSV, put the file in *Documents*, and import it as one of the kinds for ERPNext: items, customers, suppliers,
opening stock, open sales orders or open purchase orders.

WenQuest Ops matches the columns to ERPNext's fields: by the usual column names of QuickBooks, NetSuite, SAP Business
One and Odoo exports, or with AI, which quotes the columns it used. You check and change the mapping. The preview
shows every row: ready, skipped because ERPNext has it already, or waiting because it names something ERPNext does
not have yet. A value that cannot be read stays unknown; nothing is guessed.

When you sign, the rows are written into ERPNext. Items, customers and suppliers are created. Opening stock becomes one
stock reconciliation, and order lines with the same order number become one order; both are drafts in ERPNext for
someone to check and submit, unless you choose to submit them at once. Every row's outcome is kept. If ERPNext refuses
a row or cannot be reached, the row is skipped with the reason: import the file again later and only the rest comes in.
