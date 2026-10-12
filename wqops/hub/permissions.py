"""What each role may do (ADR-0005). The owner may do everything."""

from __future__ import annotations

PERMISSIONS = {
    "dashboard:view": "See the dashboard and the ops hub",
    "inventory:view": "See items, stock and warehouses",
    "sales:view": "See customers and sales orders",
    "purchasing:view": "See suppliers and purchase orders",
    "purchasing:draft": "Draft purchase orders for someone to confirm",
    "quality:view": "See inspections, nonconformances and CAPA",
    "quality:edit": "Record inspections, nonconformances, 8D and CAPA",
    "ai:use": "Ask the AI assistant and receive drafts",
    "ai:configure": "Configure the AI assistant",
    "users:view": "See who has access",
    "users:manage": "Set passwords, activate and deactivate people",
    "settings:edit": "Change platform settings",
}

_VIEW = {"dashboard:view", "inventory:view", "sales:view", "purchasing:view", "quality:view"}
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(PERMISSIONS),
    "ops_manager": frozenset(_VIEW | {"purchasing:draft", "quality:edit", "ai:use", "users:view"}),
    "warehouse": frozenset({"dashboard:view", "inventory:view", "purchasing:view", "quality:view", "ai:use"}),
    "purchasing": frozenset({"dashboard:view", "inventory:view", "purchasing:view", "purchasing:draft",
                             "quality:view", "ai:use"}),
    "sales": frozenset({"dashboard:view", "inventory:view", "sales:view", "ai:use"}),
    "quality": frozenset({"dashboard:view", "inventory:view", "purchasing:view", "quality:view", "quality:edit",
                          "ai:use"}),
    "ai_specialist": frozenset(_VIEW | {"ai:use", "ai:configure", "users:view"}),
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
