---
title: Document library
group: Documents
order: 1
summary: Bring your files in, check what the AI proposes, find problems.
try:
  - id: overview
    text: Sign in as **Jordan** (Quality) and open *Documents* in the sidebar. Read the *Overview* tab.
    to: /documents
    expect: the counts of the library, how many files wait for review, and a table by process and type where processes with nothing in the library yet say *none yet*.
    tour:
      - target: '[data-help="docs-tabs"]'
        text: Overview, Problems, To review, Library and Imports. Each tab is one view of the same library.
      - target: '[data-help="docs-overview"]'
        path: /documents?tab=overview
        text: Documents in the library by process and type. Click a number to see them; the last column counts the problems found.
  - id: imports
    text: 'Open the *Imports* tab and find *Demo: Harbor Lane QMS folder*.'
    to: /documents?tab=imports
    expect: 22 files, 1 identical to another file, already classified, with a link to review the proposals.
    tour:
      - target: '[data-help="docs-import"]'
        path: /documents?tab=imports
        text: One box per upload. Before classifying, it says how many files the AI would read and about how many tokens.
      - target: '[data-help="docs-drop"]'
        text: To bring your own files in, drop files, folders or zip files here.
  - id: confirm-record
    text: Open the *To review* tab and open **Internal audit report 2026-03.docx**. Check each field against the quote under it, set the type to *Record* if it is not, and choose *Confirm*.
    to: /documents?tab=review
    expect: the status "kept" and, under *File*, "Frozen" with a fingerprint. Records are kept at once, with no approval.
    tour:
      - target: '[data-help="docs-review-list"]'
        path: /documents?tab=review
        text: Every proposal with where it came from (AI or rules) and how sure it is. Open a file to check it.
      - target: '[data-help="doc-proposal"]'
        text: Each field with the words of the file it was taken from. A quote not found in the file is marked; check that field.
        elsewhere: Open a file from the To review tab first.
      - target: '[data-help="doc-confirm"]'
        text: Confirm it, or give a reason and choose Not a document to keep.
        elsewhere: Open a file that still waits for review.
  - id: duplicate
    text: Open the *Problems* tab. On the problem *Same file 2 times*, choose *Not keep this copy* next to **copy of F-QA-012 Nonconformance Report.docx**.
    to: /documents?tab=problems
    expect: '"Copy not kept." and the problem is gone. The other file is marked *keep this one* until then.'
    tour:
      - target: '[data-help="docs-problems"]'
        path: /documents?tab=problems
        text: Found by fixed checks. Choose a process to see only its problems. Nothing changes until you act.
  - id: old-revision
    text: In the same tab, find **QP-08** with 2 revisions. Choose *Keep as obsolete* next to rev B, the file in the *old* folder.
    to: /documents?tab=problems
    expect: '"Kept as obsolete." Rev B stays in the library, marked obsolete, and is never used.'
  - id: number
    text: Open **torque check for anchors.txt**, a work instruction without a number. Choose *Use the suggested number*, then *Confirm*.
    to: /documents?tab=review
    expect: the number field takes a number in the company's own style; once confirmed, the work instruction is a draft.
    tour:
      - target: '[data-help="doc-file"]'
        text: The file as uploaded. With a number, it also offers a standard name for downloads; the stored original keeps its name.
        elsewhere: Open a file from the library first.
      - target: '[data-help="docs-numbering"]'
        path: /documents?tab=problems
        text: How suggested numbers are made. Without a rule of your own, the style is learned from your numbers.
  - id: search
    text: Open the *Library* tab, choose *All files* and search for **receiving inspection**.
    to: /documents?tab=library
    expect: the files with those words, each with a bit of its text and the words marked.
    tour:
      - target: '[data-help="docs-library-filter"]'
        path: /documents?tab=library
        text: Filter by status, process and type. The search reads the text of the files, not only their names.
blocks:
  - text: Files of other kinds, such as programs, and files larger than 50 MB are not taken.
    test: tests/test_documents.py::test_import_stores_files_once_and_flags_duplicates
  - text: Only proposals with high confidence and every quote found can be confirmed together; the others are opened and checked one by one.
    test: tests/test_documents.py::test_rules_classification_review_and_kept_records
  - text: A file is marked as not to keep only with a reason.
    test: tests/test_documents.py::test_rules_classification_review_and_kept_records
  - text: An older revision is kept as obsolete only with a reason, and only while it waits for review or is a draft.
    test: tests/test_document_checks.py::test_keep_older_revision_as_obsolete
  - text: The file of a kept record cannot be replaced, and nothing in the library or its history can be deleted, not even in the database.
    test: tests/test_documents.py::test_rules_classification_review_and_kept_records
  - text: A numbering rule must be a prefix followed by {seq}, such as F-{process}-{seq}.
    test: tests/test_document_checks.py::test_numbering_rules_need_a_sensible_shape
questions:
  - q: Does anything go to the AI when I upload files?
    a: No. The text is read on your own server. The AI reads the files only when you choose *Classify with AI* on the *Imports* tab, and only with the company's own key.
  - q: Why can I not select the demo proposals to confirm together?
    a: Only proposals with high confidence and every quote found in the file can. Files classified by rules have low confidence, so open each one.
  - q: Does WenQuest Ops rename my files?
    a: No. The stored original keeps its name. A document's page offers a standard name, such as QP-05 Receiving Inspection Rev D.pdf, for downloads.
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

- Proposals with high confidence and every quote found can be confirmed together: on the *To review* tab choose
  *Select the ... high-confidence*, then *Confirm ... selected*.
- Open the others, correct what is wrong and *Confirm*. Your corrections are remembered and given to the AI next
  time, so it learns how your company names and sorts things.
- A file that is not worth keeping (a stray copy, a scrap note): give the reason and choose *Not a document to keep*.

## Overview

The *Overview* tab counts the documents by process and type. A process with *none yet* has no document in the
library, a first sign of a gap; the *Problems* column counts what the checks found for each process.

## Problems

![Problems the checks found](img/document-problems.webp)

The *Problems* tab lists what fixed checks found in the library. They never change anything by themselves:

- **Same file twice**: keep one, choose *Not keep this copy* for the others.
- **Several revisions of one number**: the current one is marked; choose *Keep as obsolete* for the older ones, so
  their history stays findable but they are never used.
- **One number for different documents**, or the same revision twice: give one of them another number or revision.
- **No number, no revision, no effective date**: a number is suggested in your own style (*Use the suggested
  number*, then confirm or save).
- **Forms a procedure names that are not in the library**, forms without any record, records without a procedure,
  and processes with no documents: the first view of the gaps in your system.

**Numbering.** Suggested numbers follow the convention learned from the numbers your documents already have (for
example F-QA-013 after F-QA-012). You can set your own rule per type, such as `F-{process}-{seq}` with 3 digits.
A document's page also offers its standard file name (`QP-05 Receiving Inspection Rev D.pdf`) for downloads; the
stored original keeps its own name.
