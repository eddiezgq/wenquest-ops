"""Part categories of the PLM module (ADR-0026 item 9): the categories and fields of the WenQuest sewing machine
design software's own parts library (eddiezgq/WenQuest services/gateway/app/sewcore/partlib.py), with the general
categories of a machine builder added. Each field: key, label, unit, min, max, required; min/max None means text.

Plain data: no AI, no network.
"""

from __future__ import annotations

from wqops import i18n as I18N


def f(key, label, unit="", lo=None, hi=None, req=False):  # noqa: PLR0917 - a compact table row
    return {"key": key, "label": label, "unit": unit, "min": lo, "max": hi, "required": req}


CATEGORIES: dict[str, dict] = {
    # from the sewing machine parts library
    "motor": {"label": "Servo or main motor", "prefix": "MOT", "fields": [
        f("power_w", "Rated power", "W", 10, 20000, True), f("rated_nm", "Rated torque", "N·m", 0.01, 200, True),
        f("peak_nm", "Peak torque", "N·m", 0.01, 600, True), f("rated_rpm", "Rated speed", "r/min", 100, 20000, True),
        f("max_rpm", "Maximum speed", "r/min", 100, 20000, True),
        f("inertia", "Rotor inertia", "×10⁻⁴ kg·m²", 0.001, 500, True),
        f("flange", "Flange size", "mm", 20, 300), f("length", "Body length", "mm", 20, 600),
        f("shaft_d", "Shaft diameter", "mm", 3, 60)]},
    "needle": {"label": "Needle", "prefix": "NDL", "fields": [
        f("nm", "Needle size Nm", "", 40, 250, True), f("blade_d", "Blade diameter", "mm", 0.4, 2.5, True),
        f("shank_d", "Shank diameter", "mm", 1.0, 4.0), f("length", "Overall length", "mm", 20, 60)]},
    "needlebar": {"label": "Needle bar assembly", "prefix": "NBR", "fields": [
        f("mass", "Mass", "kg", 0.01, 1.0, True), f("d", "Bar diameter", "mm", 3, 20),
        f("length", "Length", "mm", 40, 300)]},
    "bushing": {"label": "Needle bar bushing", "prefix": "BSH", "fields": [
        f("load", "Allowed load", "N", 50, 5000, True), f("d_in", "Inner diameter", "mm", 3, 30),
        f("d_out", "Outer diameter", "mm", 5, 50), f("length", "Length", "mm", 5, 80)]},
    "belt": {"label": "Timing belt", "prefix": "BLT", "fields": [
        f("EA", "Tensile stiffness EA", "kN", 10, 2000, True), f("width", "Belt width", "mm", 3, 100),
        f("pitch", "Pitch", "mm", 1, 20)]},
    "pulley": {"label": "Timing pulley", "prefix": "PUL", "fields": [
        f("r", "Pitch radius", "mm", 3, 150, True), f("teeth", "Teeth", "", 8, 200),
        f("width", "Belt width", "mm", 3, 100), f("bore", "Bore", "mm", 2, 60)]},
    "link": {"label": "Crank or link (two-hole plate)", "prefix": "LNK", "fields": [
        f("L", "Hole distance", "mm", 5, 200, True), f("d1", "Large hole diameter", "mm", 2, 60),
        f("d2", "Small hole diameter", "mm", 1, 60), f("t", "Thickness", "mm", 1, 40),
        f("material", "Material")]},
    "frame": {"label": "Frame, bed or beam", "prefix": "FRM", "fields": [
        f("mass", "Mass", "kg", 0.1, 2000), f("material", "Material")]},
    # sewing machine parts the library does not have yet
    "hook": {"label": "Rotary hook", "prefix": "HOK", "fields": [
        f("model", "Model", req=True), f("bobbin_d", "Bobbin diameter", "mm", 15, 40, True),
        f("max_spm", "Maximum speed", "stitches/min", 500, 10000), f("material", "Material")]},
    "feeddog": {"label": "Feed dog", "prefix": "FDG", "fields": [
        f("rows", "Tooth rows", "", 1, 6, True), f("pitch", "Tooth pitch", "mm", 0.5, 5, True),
        f("length", "Length", "mm", 5, 60), f("material", "Material")]},
    # general parts of a machine builder
    "shaft": {"label": "Shaft", "prefix": "SFT", "fields": [
        f("d", "Main diameter", "mm", 2, 200, True), f("length", "Length", "mm", 5, 3000, True),
        f("material", "Material"), f("heat_treatment", "Heat treatment")]},
    "cam": {"label": "Cam", "prefix": "CAM", "fields": [
        f("base_r", "Base circle radius", "mm", 2, 300, True), f("lift", "Lift", "mm", 0.1, 200, True),
        f("material", "Material")]},
    "bearing": {"label": "Bearing", "prefix": "BRG", "fields": [
        f("designation", "Designation", req=True), f("d", "Bore d", "mm", 1, 500, True),
        f("D", "Outer diameter D", "mm", 3, 800, True), f("B", "Width B", "mm", 1, 300, True)]},
    "fastener": {"label": "Fastener", "prefix": "FST", "fields": [
        f("spec", "Size", req=True), f("standard", "Standard"), f("grade", "Property class")]},
    "electronic": {"label": "Electronic part", "prefix": "ELC", "fields": [
        f("spec", "Specification", req=True), f("maker_part", "Maker part number")]},
    "assembly": {"label": "Assembly or machine", "prefix": "ASM", "fields": [
        f("model", "Model"), f("description_short", "Short description")]},
    "other": {"label": "Other", "prefix": "OTH", "fields": [f("spec", "Specification"), f("material", "Material")]},
}


def get(key: str) -> dict:
    if key not in CATEGORIES:
        raise KeyError(key)
    return CATEGORIES[key]


def shown() -> list[dict]:
    """The categories with their labels in the reader's language."""
    out = []
    for k, c in CATEGORIES.items():
        out.append({"key": k, "label": I18N.label(c["label"]), "prefix": c["prefix"],
                    "fields": [{**x, "label": I18N.label(x["label"]), "unit": I18N.label(x["unit"]) or ""}
                               for x in c["fields"]]})
    return out
