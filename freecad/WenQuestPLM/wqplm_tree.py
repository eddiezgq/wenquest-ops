"""WenQuest PLM add-on for FreeCAD (ADR-0026, 26e): the model tree as parts and assemblies.

Plain Python, no FreeCAD needed (tested on its own). The FreeCAD side (wqplm_doc.py) turns the document into
``items``: each {"name", "label", "kind": "assembly" | "solid" | "link", "children": [names], "target": name,
"code", "material", "volume_mm3", "mass_kg", "placement": {"p": [x, y, z], "q": [x, y, z, w]}} (where the object
sits in its assembly; a link's own placement). This gives what the PLM inbox takes:
{"nodes": [{"key", "code", "name", ...}], "links": [{"parent", "child", "qty", "placements"}]}; placements only
when every use of the pair has one (round 124, 27a).
"""
from collections import Counter


def build(items, title="Model"):
    """Links resolve to what they point at; the same solid used twice counts 2. Several top objects get one
    assembly named after the document above them."""
    by = {i["name"]: i for i in items}

    def real(name, seen=()):
        i = by.get(name)
        while i is not None and i["kind"] == "link":
            if i["name"] in seen:
                return None
            seen = (*seen, i["name"])
            i = by.get(i.get("target"))
        return i

    used = Counter()
    links = Counter()
    where = {}

    def put(pair, obj):
        pl = (by.get(obj) or {}).get("placement")
        got = where.get(pair, [])
        where[pair] = None if pl is None or got is None else [*got, pl]

    for i in items:
        if i["kind"] != "assembly":
            continue
        for c in i.get("children") or []:
            r = real(c)
            if r is None or r["name"] == i["name"]:
                continue
            links[(i["name"], r["name"])] += 1
            used[r["name"]] += 1
            put((i["name"], r["name"]), c)
    parts = [i for i in items if i["kind"] in ("assembly", "solid")]
    tops = [i["name"] for i in parts if not used[i["name"]]]
    nodes = []
    for i in parts:
        n = {"key": i["name"], "code": i.get("code") or "", "name": i.get("label") or i["name"]}
        for k in ("material", "volume_mm3", "mass_kg"):
            if i.get(k) not in (None, ""):
                n[k] = i[k]
        nodes.append(n)
    if len(tops) > 1:
        root = "__document__"
        nodes.append({"key": root, "code": "", "name": title})
        for t in tops:
            links[(root, t)] += 1
            put((root, t), t)
    return {"nodes": nodes, "links": [{"parent": p, "child": c, "qty": n,
                                       **({"placements": where[(p, c)]} if where.get((p, c)) else {})}
                                      for (p, c), n in sorted(links.items())]}
