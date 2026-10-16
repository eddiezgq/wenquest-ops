---
title: Document library
group: Documents
order: 1
summary: Bring your files in, check what the AI proposes, find problems.
---

The document library keeps the company's procedures, work instructions, forms, records and certificates in one place
that can be searched, with the right revision of each.

![The document library](img/documents.webp)

## Bring your files in

Drop files, whole folders or zip files on the *Documents* page (or use *choose files* / *choose a folder*).
PDF, Word, Excel, CSV, text and scanned images are taken, up to 50 MB a file. Folder names are kept: they help to
sort the files. The text is read on your own server; scans are read with OCR.

Nothing goes to the AI until you choose. On the *Imports* tab, each import shows how many files the AI would read and
roughly how many tokens that is (with the company's own key); then choose **Classify with AI**. Without a key the
files are classified by rules (file names, folders and labels such as "Doc No."), with limited accuracy.

## Review what the AI proposes

![A proposal with the file's own words beside each field](img/document-review.webp)

For each file the AI proposes the type, the process, the number, title, revision, effective date and owner, a short
summary, and the forms and records a procedure names. **Every field quotes the file.** WenQuest Ops checks each
quote against the file; a quote it cannot find is marked, and you should check that field.

- Proposals with high confidence and every quote found can be confirmed together (*To review* → *Select* →
  *Confirm*).
- Open the others, correct what is wrong and *Confirm*. Your corrections are remembered and given to the AI next
  time, so it learns how your company names and sorts things.
- A file that is not worth keeping (a stray copy, a scrap note): give the reason and choose *Not a document to keep*.

## Overview

The *Overview* tab counts the documents by process and type. A process with *none yet* has no document in the
library — a first sign of a gap; the *Problems* column counts what the checks found for each process.

## Problems

![Problems the checks found](img/document-problems.webp)

The *Problems* tab lists what fixed checks found in the library — they never change anything by themselves:

- **Same file twice** — keep one, choose *Not keep this copy* for the others.
- **Several revisions of one number** — the current one is marked; keep the older ones *as obsolete*, so their
  history stays findable but they are never used.
- **One number for different documents**, or the same revision twice — give one of them another number or revision.
- **No number, no revision, no effective date** — a number is suggested in your own style (*Use the suggested
  number*, then confirm or save).
- **Forms a procedure names that are not in the library**, forms without any record, records without a procedure,
  and processes with no documents — the first view of the gaps in your system.

**Numbering.** Suggested numbers follow the convention learned from the numbers your documents already have (for
example F-QA-013 after F-QA-012). You can set your own rule per type, such as `F-{process}-{seq}` with 3 digits.
A document's page also offers its standard file name (`QP-05 Receiving Inspection Rev D.pdf`) for downloads; the
stored original keeps its own name.
