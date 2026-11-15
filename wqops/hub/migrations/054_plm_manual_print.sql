-- PLM 33c (WenQuest round 135): each edition of the parts manual as two PDFs, for screen (pdf_sha: colour pictures,
-- links) and for print (print_sha: line drawings as vectors, 3 mm bleed). Editions made before have only the first.
alter table plm_manuals add column print_sha text;

-- an edition stays as it was made (052): the column is written with the row, never later
