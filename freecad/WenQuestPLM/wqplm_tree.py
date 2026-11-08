"""WenQuest PLM add-on for FreeCAD (ADR-0026, 26e): the model tree as parts and assemblies.

Plain Python, no FreeCAD needed (tested on its own). The FreeCAD side (wqplm_doc.py) turns the document into
``items``: each {"name", "label", "kind": "assembly" | "solid" | "link", "children": [names], "target": name,
"code", "material", "volume_mm3", "mass_kg"}. This gives what the PLM inbox takes:
{"nodes": [{"key", "code", "name", ...}], "links": [{"parent", "child", "qty"}]}.
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
    for i in items:
        if i["kind"] != "assembly":
            continue
        for c in i.get("children") or []:
            r = real(c)
            if r is None or r["name"] == i["name"]:
                continue
            links[(i["name"], r["name"])] += 1
            used[r["name"]] += 1
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
    return {"nodes": nodes, "links": [{"parent": p, "child": c, "qty": n} for (p, c), n in sorted(links.items())]}
