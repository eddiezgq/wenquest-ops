# Documents

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

## Controlled documents

- **Records, certificates and outside documents** are kept as soon as they are confirmed. Their file is frozen: it
  can never be replaced.
- **Procedures, work instructions and forms** become drafts. *Send for approval*; then someone who did not upload,
  confirm or send it approves it with their password. It becomes **effective** and its file is frozen.
- **A new revision**: on the effective document, upload the next revision. It goes through approval too; when it is
  approved, the old revision becomes obsolete automatically (and stays available).
- *Make obsolete* needs a reason. The history and signatures cannot be changed or deleted.

## Overview

The *Overview* tab counts the documents by process and type. A process with *none yet* has no document in the
library — a first sign of a gap.
