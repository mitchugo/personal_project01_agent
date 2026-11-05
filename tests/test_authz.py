"""Permission policy tests: the documented matrix, default deny."""

import pytest

from app.authz import CONTACT_FIELDS, Action, authorize
from app.models import Role

STAFF = [Role.SUPPORT_AGENT, Role.SUPERVISOR]


@pytest.mark.parametrize("role", STAFF)
def test_staff_may_read_customers(role):
    assert authorize(role, Action.READ_CUSTOMER).allowed


@pytest.mark.parametrize("role", STAFF)
def test_staff_may_update_contact_fields(role):
    assert authorize(role, Action.UPDATE_CUSTOMER, CONTACT_FIELDS).allowed


@pytest.mark.parametrize("action", list(Action))
def test_tenant_admin_is_denied_every_customer_action(action):
    decision = authorize(Role.TENANT_ADMIN, action, frozenset({"email"}))
    assert not decision.allowed
    assert decision.reason == "role_not_permitted"


@pytest.mark.parametrize("role", STAFF)
@pytest.mark.parametrize("field", ["policy_number", "policy_note", "full_name", "tenant_id", "customer_id"])
def test_non_contact_fields_are_not_updatable_by_anyone_yet(role, field):
    decision = authorize(role, Action.UPDATE_CUSTOMER, frozenset({"email", field}))
    assert (decision.allowed, decision.reason) == (False, "field_not_permitted")


def test_update_with_no_fields_is_denied():
    assert authorize(Role.SUPPORT_AGENT, Action.UPDATE_CUSTOMER).reason == "no_fields"


def test_unknown_action_is_denied_by_default():
    assert not authorize(Role.SUPERVISOR, "delete_customer").allowed  # type: ignore[arg-type]
