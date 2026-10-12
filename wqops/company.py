"""Company manifest (docs/plan.md, Phase 1 item 2).

One ``company.yaml`` describes a business: the company itself, its sites, warehouses, departments, people and the
modules it turns on. Installation (item 3) creates the ERPNext company from it; the ops hub (item 6) reads it.

Adapted from the plant manifest of the WenQuest digital factory (freecad-ai-parts, factory/factory/plant.py).

    python -m wqops.company check company.yaml
    python -m wqops.company template company.xlsx     # Excel template filled with the demo company
    python -m wqops.company import filled.xlsx company.yaml
    python -m wqops.company export-demo company.yaml
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

SCHEMA_VERSION = 1
ROLES = ("owner", "ops_manager", "warehouse", "purchasing", "sales", "quality", "ai_specialist")
ROLE_LABELS = {"owner": "Owner", "ops_manager": "Operations Manager", "warehouse": "Warehouse",
               "purchasing": "Purchasing", "sales": "Sales", "quality": "Quality", "ai_specialist": "AI Specialist"}
SITE_KINDS = ("office", "warehouse", "plant", "store")
WAREHOUSE_KINDS = ("stores", "receiving", "finished_goods", "shipping", "quarantine", "transit")
MODULES = ("core", "hub", "ai", "quality", "warehousing", "production")
REQUIRED_MODULES = ("core", "hub")
WEIGHT_UNITS = ("lb", "kg")
LENGTH_UNITS = ("in", "cm")
DATE_FORMATS = ("mm-dd-yyyy", "dd-mm-yyyy", "yyyy-mm-dd")
DEMO_DIR = Path(__file__).resolve().parents[1] / "companies"
DEMO_FILE = DEMO_DIR / "demo-harbor-lane.yaml"

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MMDD = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


class CompanyError(ValueError):
    """The manifest has errors; ``errors`` lists them as "location: message"."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(f"company manifest has {len(self.errors)} error(s):\n" +
                         "\n".join("  - " + e for e in self.errors))


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validate(m) -> list[str]:  # noqa: PLR0912, PLR0915 - one flat checklist reads best
    """Check every field; return the errors (empty list = valid)."""
    errs: list[str] = []

    def need(cond, where, msg):
        if not cond:
            errs.append(f"{where}: {msg}")
        return cond

    if not isinstance(m, dict):
        return ["manifest: not a mapping"]
    need(m.get("version") == SCHEMA_VERSION, "version", f"must be {SCHEMA_VERSION}")
    need(isinstance(m.get("demo", False), bool), "demo", "true or false")

    c = m.get("company")
    if need(isinstance(c, dict), "company", "required"):
        for k in ("name", "abbr", "country", "currency", "timezone"):
            need(_text(c.get(k)), f"company.{k}", "required")
        if _text(c.get("abbr")):
            need(c["abbr"].isalnum() and len(c["abbr"]) <= 6, "company.abbr", "letters and digits only, at most 6")
        if _text(c.get("currency")):
            need(re.fullmatch(r"[A-Z]{3}", c["currency"]) is not None, "company.currency", "ISO code such as USD")
        if _text(c.get("timezone")):
            try:
                from zoneinfo import ZoneInfo  # noqa: PLC0415

                ZoneInfo(c["timezone"])
            except Exception:
                errs.append(f"company.timezone: unknown time zone {c['timezone']!r} (e.g. America/New_York)")
        fy = c.get("fiscal_year_start", "01-01")
        need(isinstance(fy, str) and _MMDD.match(fy), "company.fiscal_year_start", "MM-DD, e.g. 01-01")
        need(c.get("date_format", "mm-dd-yyyy") in DATE_FORMATS, "company.date_format", " / ".join(DATE_FORMATS))
        u = c.get("units") or {}
        need(isinstance(u, dict), "company.units", "a mapping")
        if isinstance(u, dict):
            need(u.get("weight", "lb") in WEIGHT_UNITS, "company.units.weight", " / ".join(WEIGHT_UNITS))
            need(u.get("length", "in") in LENGTH_UNITS, "company.units.length", " / ".join(LENGTH_UNITS))

    def ids(section, items):
        seen = set()
        for i, it in enumerate(items):
            at = f"{section}[{i}]"
            if not need(isinstance(it, dict), at, "a mapping"):
                continue
            iid = it.get("id")
            if need(isinstance(iid, str) and _ID.match(iid), f"{at}.id",
                    "lowercase letters, digits and -, up to 40"):
                need(iid not in seen, f"{at}.id", f"duplicate id {iid!r}")
                seen.add(iid)
            need(_text(it.get("name")), f"{at}.name", "required")
        return seen

    sites = m.get("sites") or []
    need(isinstance(sites, list) and sites, "sites", "at least one site")
    site_ids = ids("sites", sites if isinstance(sites, list) else [])
    for i, s in enumerate(sites if isinstance(sites, list) else []):
        if isinstance(s, dict):
            need(s.get("kind") in SITE_KINDS, f"sites[{i}].kind", " / ".join(SITE_KINDS))
            a = s.get("address")
            if a is not None and need(isinstance(a, dict), f"sites[{i}].address", "a mapping"):
                for k in ("line1", "city", "postal_code", "country"):
                    need(_text(a.get(k)), f"sites[{i}].address.{k}", "required when an address is given")

    whs = m.get("warehouses") or []
    need(isinstance(whs, list) and whs, "warehouses", "at least one warehouse")
    ids("warehouses", whs if isinstance(whs, list) else [])
    for i, w in enumerate(whs if isinstance(whs, list) else []):
        if isinstance(w, dict):
            need(w.get("site") in site_ids, f"warehouses[{i}].site", "must be one of the site ids")
            need(w.get("kind") in WAREHOUSE_KINDS, f"warehouses[{i}].kind", " / ".join(WAREHOUSE_KINDS))

    depts = m.get("departments") or []
    need(isinstance(depts, list), "departments", "a list")
    dept_ids = ids("departments", depts if isinstance(depts, list) else [])

    people = m.get("people") or []
    need(isinstance(people, list), "people", "a list")
    emails = set()
    owners = 0
    for i, p in enumerate(people if isinstance(people, list) else []):
        at = f"people[{i}]"
        if not need(isinstance(p, dict), at, "a mapping"):
            continue
        need(_text(p.get("name")), f"{at}.name", "required")
        e = p.get("email")
        if need(isinstance(e, str) and _EMAIL.match(e), f"{at}.email", "a valid email address"):
            need(e.lower() not in emails, f"{at}.email", f"duplicate email {e!r}")
            emails.add(e.lower())
        roles = p.get("roles")
        if need(isinstance(roles, list) and roles, f"{at}.roles", "at least one role"):
            bad = [r for r in roles if r not in ROLES]
            need(not bad, f"{at}.roles", f"unknown role(s) {bad}; use {', '.join(ROLES)}")
            owners += "owner" in roles
        if p.get("department") is not None:
            need(p["department"] in dept_ids, f"{at}.department", "must be one of the department ids")
    if people:
        need(owners >= 1, "people", "at least one person with the owner role")

    mods = m.get("modules") or []
    if need(isinstance(mods, list) and mods, "modules", "list the modules to turn on"):
        bad = [x for x in mods if x not in MODULES]
        need(not bad, "modules", f"unknown module(s) {bad}; use {', '.join(MODULES)}")
        for r in REQUIRED_MODULES:
            need(r in mods, "modules", f"{r!r} is always required")
    return errs


def normalize(m: dict) -> dict:
    """Fill defaults so the rest of the platform never guesses."""
    m = dict(m)
    c = dict(m["company"])
    c.setdefault("fiscal_year_start", "01-01")
    c.setdefault("date_format", "mm-dd-yyyy")
    c["units"] = {"weight": "lb", "length": "in", **(c.get("units") or {})}
    m["company"] = c
    m.setdefault("demo", False)
    m.setdefault("departments", [])
    m.setdefault("people", [])
    return m


def load(path) -> dict:
    """Read, validate and normalize a manifest; raise CompanyError when invalid."""
    try:
        m = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CompanyError([f"{path}: not valid YAML ({exc})"]) from exc
    errs = validate(m)
    if errs:
        raise CompanyError(errs)
    return normalize(m)


def dump(m: dict) -> str:
    return yaml.safe_dump(m, allow_unicode=True, sort_keys=False)


def main(argv=None) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(prog="python -m wqops.company", description="Company manifest tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("manifest")
    t = sub.add_parser("template")
    t.add_argument("xlsx")
    i = sub.add_parser("import")
    i.add_argument("xlsx")
    i.add_argument("manifest")
    sub.add_parser("export-demo").add_argument("manifest")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "check":
            m = load(a.manifest)
            print(f"OK: {m['company']['name']} - {len(m['sites'])} site(s), {len(m['warehouses'])} warehouse(s), "
                  f"{len(m['people'])} people, modules {', '.join(m['modules'])}")
        elif a.cmd == "template":
            from wqops import company_xlsx  # noqa: PLC0415

            company_xlsx.write_template(a.xlsx, load(DEMO_FILE))
            print(f"Template written to {a.xlsx}")
        elif a.cmd == "import":
            from wqops import company_xlsx  # noqa: PLC0415

            m = company_xlsx.read(a.xlsx)
            Path(a.manifest).write_text(dump(m), encoding="utf-8")
            print(f"Imported {m['company']['name']} into {a.manifest}")
        else:
            Path(a.manifest).write_text(DEMO_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Demo company written to {a.manifest}")
    except CompanyError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
