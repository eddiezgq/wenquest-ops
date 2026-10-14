"""Role permissions (ADR-0005): what each role can and cannot do."""

import pytest

from wqops import company as C
from wqops.hub import permissions as P

CAN = {
    "warehouse": {"inventory:view", "ai:use"},
    "purchasing": {"purchasing:draft"},
    "sales": {"sales:view"},
    "quality": {"quality:edit", "documents:edit"},
    "ops_manager": {"quality:edit", "purchasing:draft", "users:view"},
    "ai_specialist": {"ai:configure", "users:view"},
}
CANNOT = {
    "warehouse": {"purchasing:draft", "quality:edit", "users:view", "sales:view", "settings:edit", "documents:edit"},
    "purchasing": {"quality:edit", "users:manage", "sales:view"},
    "sales": {"purchasing:draft", "quality:edit", "users:view", "documents:edit"},
    "quality": {"purchasing:draft", "users:manage", "sales:view"},
    "ops_manager": {"users:manage", "settings:edit", "ai:configure"},
    "ai_specialist": {"users:manage", "settings:edit", "purchasing:draft", "quality:edit"},
}


def test_every_role_is_defined_and_owner_has_all():
    assert set(P.ROLE_PERMISSIONS) == set(C.ROLES)
    assert P.of(["owner"]) == frozenset(P.PERMISSIONS)
    for perms in P.ROLE_PERMISSIONS.values():
        assert perms <= set(P.PERMISSIONS)
        assert "dashboard:view" in perms


@pytest.mark.parametrize("role", sorted(CAN))
def test_can_and_cannot(role):
    for p in CAN[role]:
        assert P.allows([role], p), (role, p)
    for p in CANNOT[role]:
        assert not P.allows([role], p), (role, p)


def test_everyone_sees_the_document_library():
    """ADR-0014 item 8: documents:view for all roles; documents:edit for owner, ops manager, quality, AI specialist."""
    assert all("documents:view" in perms for perms in P.ROLE_PERMISSIONS.values())
    assert {r for r, perms in P.ROLE_PERMISSIONS.items() if "documents:edit" in perms} == \
        {"owner", "ops_manager", "quality", "ai_specialist"}


def test_roles_combine_and_unknown_permission_is_an_error():
    assert P.allows(["sales", "quality"], "quality:edit") and P.allows(["sales", "quality"], "sales:view")
    assert P.of([]) == frozenset() and P.of(["nobody"]) == frozenset()
    with pytest.raises(KeyError):
        P.allows(["owner"], "launch:rockets")
