"""Model validation tests: shape and strictness only, not authorisation."""

import pytest
from pydantic import ValidationError

from app.models import Customer, KnowledgeDocument, Role, Ticket, User

VALID_USER = {
    "user_id": "ns-agent-01",
    "tenant_id": "northstar",
    "display_name": "Test Agent",
    "email": "agent@northstar.example",
    "role": "support_agent",
}


def test_valid_user_parses_role_enum():
    user = User(**VALID_USER)
    assert user.role is Role.SUPPORT_AGENT


def test_unknown_role_is_rejected():
    with pytest.raises(ValidationError):
        User(**{**VALID_USER, "role": "superuser"})


def test_unexpected_fields_are_rejected():
    # e.g. an "is_admin" flag smuggled into a payload must not be silently dropped.
    with pytest.raises(ValidationError):
        User(**VALID_USER, is_admin=True)


def test_records_are_immutable():
    user = User(**VALID_USER)
    with pytest.raises(ValidationError):
        user.role = Role.TENANT_ADMIN


@pytest.mark.parametrize("model", [User, Customer, Ticket, KnowledgeDocument])
def test_tenant_owned_models_require_tenant_id(model):
    assert model.model_fields["tenant_id"].is_required()


def test_ids_must_match_stable_id_pattern():
    with pytest.raises(ValidationError):
        User(**{**VALID_USER, "user_id": "NS Agent 01; DROP TABLE users"})
