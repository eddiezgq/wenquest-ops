---
title: Old ledgers
group: Documents
order: 3
summary: Bring an old NCR log, CAPA log or supplier list in.
needs: quality:view
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
