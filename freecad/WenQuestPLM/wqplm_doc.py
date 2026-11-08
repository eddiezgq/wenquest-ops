"""WenQuest PLM add-on: the FreeCAD document as items for wqplm_tree.build, and the STEP of each solid.

Assemblies: App::Part and Assembly objects. Solids: PartDesign bodies and Part features with a shape that are not
inside a body. Links point at what they link. Groups are looked through. A part's code comes from a property named
PartNumber, Code or WQCode if it has one; material and mass from its ShapeMaterial (FreeCAD 1.0+) when set."""
import os
import re
import tempfile

ASSEMBLY = ("App::Part", "Assembly::AssemblyObject")


def _code(o):
    for p in ("PartNumber", "Code", "WQCode"):
        if p in o.PropertiesList and str(getattr(o, p) or "").strip():
            return str(getattr(o, p)).strip()
    return ""


def _density(o):
    """kg/m^3 from a material that was set (not FreeCAD's default), or None."""
    if not _material(o):
        return None
    try:
        d = str(o.ShapeMaterial.Properties.get("Density", ""))
    except Exception:
        return None
    m = re.match(r"\s*([0-9.eE+-]+)\s*(kg/m\^3|kg/m3|g/cm\^3|g/cm3)?", d)
    if not m:
        return None
    v = float(m.group(1))
    return v * 1000 if (m.group(2) or "").startswith("g/") else v


def _material(o):
    try:
        n = o.ShapeMaterial.Name
        return "" if n in ("", "Default") else n
    except Exception:
        return str(getattr(o, "Material", "") or "")


def _kids(o):
    out = []
    for c in getattr(o, "Group", []) or []:
        if c.TypeId == "App::DocumentObjectGroup":
            out += _kids(c)
        else:
            out.append(c)
    return out


def _is_solid(o):
    if o.TypeId == "PartDesign::Body":
        return True
    if not hasattr(o, "Shape") or o.TypeId.startswith(("Sketcher::", "PartDesign::", "App::", "Assembly::")):
        return False
    if any(p.TypeId == "PartDesign::Body" for p in o.InList):
        return False
    try:
        return o.Shape.Volume > 0
    except Exception:
        return False


def items(doc):
    out = []
    for o in doc.Objects:
        if o.TypeId in ASSEMBLY:
            out.append({"name": o.Name, "label": o.Label, "kind": "assembly", "code": _code(o),
                        "children": [c.Name for c in _kids(o)]})
        elif o.TypeId == "App::Link":
            t = o.LinkedObject
            out.append({"name": o.Name, "label": o.Label, "kind": "link", "target": t.Name if t else None})
        elif _is_solid(o):
            vol = float(o.Shape.Volume)
            d = _density(o)
            it = {"name": o.Name, "label": o.Label, "kind": "solid", "code": _code(o), "volume_mm3": round(vol, 3),
                  "material": _material(o)}
            if d:
                it["mass_kg"] = round(vol * 1e-9 * d, 6)
            out.append(it)
    return out


def steps(doc, data):
    """The STEP of every solid node: node key -> (file name, bytes)."""
    import Import
    out = {}
    tmp = tempfile.mkdtemp(prefix="wqplm-")
    for n in data["nodes"]:
        o = doc.getObject(n["key"])
        if o is None or o.TypeId in ASSEMBLY:
            continue
        safe = re.sub(r"[^\w.-]+", "_", n["name"])[:60] or n["key"]
        path = os.path.join(tmp, safe + ".step")
        Import.export([o], path)
        with open(path, "rb") as f:
            out[n["key"]] = (safe + ".step", f.read())
    return out


def push(doc):
    """Send the document to the PLM inbox. Returns the server's answer ({id, parts, status})."""
    import wqplm_net as N
    import wqplm_tree as T
    data = T.build(items(doc), doc.Label)
    if not data["nodes"]:
        raise N.NetError("模型里没有零件 / no parts in this model")
    model = None
    if doc.FileName and os.path.exists(doc.FileName):
        with open(doc.FileName, "rb") as f:
            model = (os.path.basename(doc.FileName), f.read())
    return N.send(data, steps(doc, data), model)
