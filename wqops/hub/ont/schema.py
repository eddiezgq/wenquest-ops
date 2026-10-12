"""Ontology definitions (ADR-0007): read wqops/ontology/*.yaml, check them, index types, links and reverse links.

Adapted from freecad-ai-parts factory/digital/hub/ont/schema.py (Round 17A): English only, one permission per domain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from wqops.hub import permissions as P

DIR = Path(__file__).resolve().parents[2] / "ontology"
MATURITY = {"have": "Synced", "erp": "In ERPNext, not synced yet"}
PROP_TYPES = {"str", "num", "int", "bool", "date", "json"}
UNITS = {"currency", "%", "days"}


class OntologyError(ValueError):
    pass


@dataclass
class Ontology:
    domains: list[dict] = field(default_factory=list)
    types: dict[str, dict] = field(default_factory=dict)          # name -> spec (with domain, view, props, links)
    links: dict[tuple[str, str], dict] = field(default_factory=dict)
    incoming: dict[str, list[tuple[str, str, dict]]] = field(default_factory=dict)

    def type(self, name: str) -> dict:
        if name not in self.types:
            raise KeyError(f"no object type {name!r}")
        return self.types[name]

    def link(self, frm: str, name: str) -> dict:
        if (frm, name) not in self.links:
            raise KeyError(f"no link {frm}.{name}")
        return self.links[(frm, name)]

    def can_see(self, roles, type_name: str) -> bool:
        t = self.types.get(type_name)
        return t is not None and P.allows(roles, t["view"])

    def public(self, roles) -> list[dict]:
        """The ontology as the web page and the AI see it: only domains this person may view."""
        out = []
        for d in self.domains:
            if not P.allows(roles, d["view"]):
                continue
            out.append({"domain": d["domain"], "label": d["label"], "types": [{
                "name": n, "label": self.types[n]["label"], "maturity": self.types[n]["maturity"],
                "maturity_label": MATURITY[self.types[n]["maturity"]], "source": self.types[n]["source"],
                "key": self.types[n]["key"],
                "props": [{"name": p, "label": s["l"], "type": s["t"], "unit": s.get("u", "")}
                          for p, s in self.types[n]["props"].items()],
                "links": [{"name": ln, "to": s["to"], "label": s["l"], "inverse": s["inv"]}
                          for ln, s in self.types[n]["links"].items() if self.can_see(roles, s["to"])],
            } for n in d["types"]]})
        return out


def load(path: Path = DIR) -> Ontology:  # noqa: PLR0912 - one check per rule, kept in one place
    files = sorted(Path(path).glob("*.yaml"))
    if not files:
        raise OntologyError(f"no ontology files in {path}")
    onto = Ontology()
    seen: set[str] = set()
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise OntologyError(f"{f.name}: not valid YAML: {exc}") from None
        if not isinstance(doc, dict):
            raise OntologyError(f"{f.name}: expected a mapping")
        for k in ("domain", "order", "label", "view", "types"):
            if k not in doc:
                raise OntologyError(f"{f.name}: missing {k}")
        if doc["domain"] in seen:
            raise OntologyError(f"{f.name}: domain {doc['domain']} is defined twice")
        if doc["view"] not in P.PERMISSIONS:
            raise OntologyError(f"{f.name}: view must be a permission ({', '.join(P.PERMISSIONS)})")
        seen.add(doc["domain"])
        d = {"domain": doc["domain"], "order": doc["order"], "label": doc["label"], "view": doc["view"], "types": []}
        for tn, ts in (doc["types"] or {}).items():
            where = f"{f.name}: {tn}"
            if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", tn):
                raise OntologyError(f"{where}: type names are UpperCamelCase")
            if tn in onto.types:
                raise OntologyError(f"{where}: type already defined in domain {onto.types[tn]['domain']}")
            for k in ("label", "maturity", "source", "key"):
                if not ts.get(k):
                    raise OntologyError(f"{where}: missing {k}")
            if ts["maturity"] not in MATURITY:
                raise OntologyError(f"{where}: maturity must be one of {', '.join(MATURITY)}")
            props = ts.get("props") or {}
            for pn, ps in props.items():
                if not isinstance(ps, dict) or ps.get("t") not in PROP_TYPES or not ps.get("l"):
                    raise OntologyError(f"{where}.{pn}: a property needs t ({', '.join(sorted(PROP_TYPES))}) and l")
                if ps.get("u") and ps["u"] not in UNITS:
                    raise OntologyError(f"{where}.{pn}: unit must be one of {', '.join(sorted(UNITS))}")
            title = ts.get("title", "{key}")
            for ref in re.findall(r"{(\w+)}", title):
                if ref != "key" and ref not in props:
                    raise OntologyError(f"{where}: title uses unknown property {ref}")
            onto.types[tn] = {**ts, "name": tn, "domain": doc["domain"], "view": doc["view"], "props": props,
                              "links": ts.get("links") or {}, "title": title}
            d["types"].append(tn)
        onto.domains.append(d)
    for tn, t in onto.types.items():
        for ln, ls in t["links"].items():
            if not isinstance(ls, dict) or not ls.get("to") or not ls.get("l") or not ls.get("inv"):
                raise OntologyError(f"{tn}.{ln}: a link needs to, l and inv")
            if ls["to"] not in onto.types:
                raise OntologyError(f"{tn}.{ln}: link target {ls['to']} is not an object type")
            onto.links[(tn, ln)] = {**ls, "frm": tn, "name": ln}
            onto.incoming.setdefault(ls["to"], []).append((tn, ln, ls))
    onto.domains.sort(key=lambda d: d["order"])
    return onto


_cache: dict[Path, Ontology] = {}


def get(path: Path = DIR) -> Ontology:
    if path not in _cache:
        _cache[path] = load(path)
    return _cache[path]


def title_of(spec: dict, key: str, props: dict) -> str:
    def rep(m):
        v = key if m.group(1) == "key" else props.get(m.group(1))
        return "" if v is None else (f"{v:g}" if isinstance(v, float) else str(v))
    return re.sub(r"\s+", " ", re.sub(r"{(\w+)}", rep, spec["title"])).strip() or key
