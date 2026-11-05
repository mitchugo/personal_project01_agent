"""Dev identity fixture tests.

These show the fixture resolves identity from the database and fails closed. They
do not show that any data access is authorised - there is no gateway yet.
"""

import inspect

import pytest
from pydantic import ValidationError

from app import fixtures
from app.identity import Principal
from app.identity.dev_fixture import (
    DevIdentityDisabledError,
    UnknownDevUserError,
    resolve_dev_principal,
)
from app.models import Role


@pytest.fixture(autouse=True)
def dev_identity_enabled(monkeypatch):
    monkeypatch.setenv("IDENTITY_MODE", "local-fixture")
    monkeypatch.delenv("APP_ENV", raising=False)


@pytest.mark.parametrize("user", fixtures.USERS, ids=lambda u: u.user_id)
def test_resolves_every_fixture_user_with_tenant_and_role_from_database(conn, user):
    principal = resolve_dev_principal(conn, user.user_id)
    assert principal == Principal(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        role=user.role,
        identity_source="local-fixture",
    )


def test_caller_cannot_supply_tenant_or_role():
    params = list(inspect.signature(resolve_dev_principal).parameters)
    assert params == ["conn", "user_id"]


def test_role_comes_from_database_not_from_the_caller(conn):
    with conn:
        conn.execute("UPDATE users SET role = 'supervisor' WHERE user_id = 'ns-agent-01'")
    assert resolve_dev_principal(conn, "ns-agent-01").role is Role.SUPERVISOR


def test_unknown_user_is_rejected(conn):
    with pytest.raises(UnknownDevUserError):
        resolve_dev_principal(conn, "ns-ghost-01")


@pytest.mark.parametrize("mode", [None, "", "oidc", "LOCAL-FIXTURE"])
def test_disabled_unless_identity_mode_is_exactly_local_fixture(conn, monkeypatch, mode):
    if mode is None:
        monkeypatch.delenv("IDENTITY_MODE", raising=False)
    else:
        monkeypatch.setenv("IDENTITY_MODE", mode)
    with pytest.raises(DevIdentityDisabledError):
        resolve_dev_principal(conn, "ns-agent-01")


def test_disabled_outside_local_environment(conn, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(DevIdentityDisabledError):
        resolve_dev_principal(conn, "ns-agent-01")


def test_principal_is_immutable(conn):
    principal = resolve_dev_principal(conn, "ns-agent-01")
    with pytest.raises(ValidationError):
        principal.tenant_id = "meridian"


def test_dev_fixture_is_not_exported_from_identity_package():
    import app.identity

    assert app.identity.__all__ == ["Principal"]
