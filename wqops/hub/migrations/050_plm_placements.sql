-- PLM step 27a (round 124): where each use of a part sits in its assembly, from FreeCAD or a STEP file:
-- [{p: [x, y, z] mm, q: [x, y, z, w]}], one per unit of quantity; empty when nobody sent it (never guessed).
alter table plm_bom_lines add column placements jsonb not null default '[]'::jsonb;
