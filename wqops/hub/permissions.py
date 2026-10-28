"""What each role may do (ADR-0005). The owner may do everything."""

from __future__ import annotations

from wqops import i18n as I18N

PERMISSIONS = {
    "dashboard:view": "See the dashboard and the ops hub",
    "inventory:view": "See items, stock and warehouses",
    "sales:view": "See customers and sales orders",
    "purchasing:view": "See suppliers and purchase orders",
    "purchasing:draft": "Draft purchase orders for someone to confirm",
    "finance:view": "See invoices, receivables and payables (ADR-0018)",
    "quality:view": "See inspections, nonconformances and CAPA",
    "quality:edit": "Record inspections, nonconformances, 8D and CAPA",
    "documents:view": "See the document library",
    "documents:edit": "Upload documents, confirm their classification and send them for approval",
    "workflows:configure": "Change quality workflows and enable versions others changed",
    "qms:configure": "Adopt quality standards, say what does not apply and link evidence",
    "data:import": "Import items, customers, suppliers, opening stock and open orders from another system (ADR-0020)",
    "ai:use": "Ask the AI assistant and receive drafts",
    "ai:configure": "Configure the AI assistant",
    "users:view": "See who has access",
    "users:manage": "Set other people's passwords (who has access comes from the company manifest)",
    "settings:edit": "Change platform settings",
    "integrations:manage": "Give machines and other systems access tokens, and revoke them (ADR-0020)",
}

_VIEW = {"dashboard:view", "inventory:view", "sales:view", "purchasing:view", "quality:view", "documents:view"}
_DOCS = {"documents:view", "documents:edit"}
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(PERMISSIONS),
    "ops_manager": frozenset(_VIEW | _DOCS | {"purchasing:draft", "quality:edit", "ai:use", "users:view",
                                             "data:import"}),
    "warehouse": frozenset({"dashboard:view", "inventory:view", "purchasing:view", "quality:view", "ai:use",
                            "documents:view"}),
    "purchasing": frozenset({"dashboard:view", "inventory:view", "purchasing:view", "purchasing:draft",
                             "quality:view", "ai:use", "documents:view"}),
    "sales": frozenset({"dashboard:view", "inventory:view", "sales:view", "ai:use", "documents:view"}),
    "quality": frozenset({"dashboard:view", "inventory:view", "purchasing:view", "quality:view", "quality:edit",
                          "ai:use", "workflows:configure", "qms:configure"} | _DOCS),
    "ai_specialist": frozenset(_VIEW | _DOCS | {"ai:use", "ai:configure", "users:view"}),
}


def of(roles) -> frozenset[str]:
    out: set[str] = set()
    for r in roles or ():
        out |= ROLE_PERMISSIONS.get(r, frozenset())
    return frozenset(out)


def allows(roles, permission: str) -> bool:
    if permission not in PERMISSIONS:
        raise KeyError(f"unknown permission {permission!r}")
    return permission in of(roles)


def describe(permission: str) -> str:
    """What a permission allows, in the reader's language (ADR-0023)."""
    return I18N.label(PERMISSIONS[permission])
