-- PLM 33b (WenQuest round 135; ADR-0030): an exploded view made by the FreeCAD add-on. It arrives waiting for a
-- person to confirm it; only a confirmed page goes into the parts manual. The line drawing (SVG) is kept for print.
alter table plm_explodes
    add column state        text not null default 'confirmed' check (state in ('pending', 'confirmed')),
    add column source       text not null default 'browser' check (source in ('browser', 'freecad')),
    add column svg_sha      text,           -- the line drawing as FreeCAD drew it (vector)
    add column line_sha     text,           -- the same drawing as a PNG
    add column confirmed_by text,
    add column confirmed_at timestamptz;
