---
title: Old ledgers
group: Documents
order: 3
summary: Bring an old NCR log, CAPA log or supplier list in.
video: old-ledgers
needs: quality:view
try:
  - id: open
    text: Sign in as **Jordan** (Quality). In *Documents*, on the *To review* tab, open **NCR log 2025-2026.xlsx**.
    to: /documents?tab=review
    expect: on the right, a box *Import as a ledger*.
    tour:
      - target: '[data-help="doc-ledger"]'
        text: Shown for Excel and CSV files. Choose what the ledger is, or let it be found from the columns.
        elsewhere: Open the NCR log from the To review tab first.
  - id: read
    text: Leave the kind of ledger as it is and choose *Read the ledger*.
    expect: the page *Import nonconformance log*, "to check", with 7 rows under the header.
    tour:
      - target: '[data-help="ledger-mapping"]'
        text: Which column fills which field, and below each choice field how the ledger's words map to ours.
        elsewhere: Choose Read the ledger on the NCR log first.
  - id: words
    text: In the *Disposition* row, find the ledger's word **RTV**. If it is left "unknown", choose *return to supplier* for it. Choose *Save the mapping*.
    expect: the rows below now show the disposition for that row; one note is left, for the status "Cancelled - entered twice".
    tour:
      - target: '[data-help="ledger-save"]'
        text: Words left unknown stay empty on the record. Save the mapping before importing.
        elsewhere: Open the ledger page first.
  - id: rows
    text: Read the rows and their notes.
    expect: 7 ready to import, each with what it would become.
    tour:
      - target: '[data-help="ledger-rows"]'
        text: What each row would become. Notes in amber are imported with the row; rows in red are skipped.
        elsewhere: Open the ledger page first.
  - id: sign
    text: Type your password and choose *Import 7 rows (sign)*.
    expect: the badge "imported" and a table of what happened to each row, with a link to each new record.
    tour:
      - target: '[data-help="ledger-import"]'
        text: Code creates the records; the AI never writes data. The import is signed with your password.
        elsewhere: Open the ledger page first.
      - target: '[data-help="ledger-outcomes"]'
        text: Each row's outcome, kept for good, and the signature below.
  - id: records
    text: Open *Quality* in the sidebar and look at the nonconformance reports.
    to: /quality
    expect: the ledger's NCRs with their own numbers (such as NCR-2025-01); the ones closed in the ledger are closed, "closed before WenQuest Ops".
  - id: again
    text: Go back to the NCR log in *Documents* and choose *Read the ledger* again.
    expect: '"7 already imported" above the rows. Importing this reading would skip them all.'
blocks:
  - text: The import is signed with your password; a wrong password is refused and the failed attempt is recorded.
    test: tests/test_ledgers.py::test_ncr_log_import_is_signed_and_happens_once
  - text: A ledger is imported once; reading the same file again skips the rows already brought in.
    test: tests/test_ledgers.py::test_ncr_log_import_is_signed_and_happens_once
  - text: A word, a date or a quantity that cannot be read one way only stays unknown; nothing is guessed.
    test: tests/test_ledgers.py::test_rows_keep_unknowns_unknown
  - text: A mapping that names a column the table does not have is refused.
    test: tests/test_ledgers.py::test_mapping_changes_by_a_person
  - text: Only Excel and CSV files are read as ledgers. Purchasing may import supplier lists only, and people without the right to edit quality records import nothing else.
    test: tests/test_ledgers.py::test_ledgers_api
questions:
  - q: The AI got a column wrong. What now?
    a: Choose the right column in *Which column is which* and choose *Save the mapping*. The rows below then show what will be imported.
  - q: Are rows closed in the ledger judged by the ISO check?
    a: No. Records imported closed are counted as history, not judged. Imported records still open are judged like any other.
  - q: What does a supplier list do?
    a: It makes a draft for each supplier not yet in ERPNext. Purchasing confirms them on *Drafts*; suppliers already in ERPNext are skipped.
---

![Which column is which](img/ledger.webp)

A spreadsheet in the library can bring its rows into WenQuest Ops. Open it and choose **Read the ledger**:

1. The AI looks at the columns and a sample of rows and proposes what the ledger is (nonconformance log, corrective
   action log or supplier list), which column fills which field, and how the ledger's words map to ours ("RTV" →
   return to supplier). Without a key the rules match the column names.
2. You check every field and every word. A word left *unknown* stays empty on the record; nothing is guessed. The
   rows below show what each would become, with notes on dates or values that could not be read.
3. **Import (sign)** with your password. Code creates the records; the AI never writes data.

- Each NCR and corrective action keeps the ledger's number and dates and names the file and row it came from. Rows
  closed in the ledger stay closed ("closed before WenQuest Ops"); open ones continue here. A corrective action is
  linked to its NCR when the ledger names one that was imported.
- A supplier list makes a draft for each supplier not yet in ERPNext; Purchasing confirms them on *Drafts*.
- A row is imported once: reading the same ledger again skips the rows already brought in.

Importing NCR and CAPA logs needs the right to edit quality records; importing a supplier list needs the right to
draft purchases.
