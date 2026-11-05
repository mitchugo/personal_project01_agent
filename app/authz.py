"""Central permission policy (docs/architecture.md §7).

One place answers "may this role perform this action?". It is deliberately
role-only: tenant scoping is enforced separately and unconditionally by the
repository, which always filters by ``Principal.tenant_id``.

Default deny: an action or role missing from the tables below is refused.
"""

from dataclasses import dataclass
from enum import Enum

from app.models import Role


class Action(str, Enum):
    READ_CUSTOMER = "read_customer"
    UPDATE_CUSTOMER = "update_customer"


# Which roles may perform each action at all.
_ALLOWED_ROLES: dict[Action, frozenset[Role]] = {
    Action.READ_CUSTOMER: frozenset({Role.SUPPORT_AGENT, Role.SUPERVISOR}),
    Action.UPDATE_CUSTOMER: frozenset({Role.SUPPORT_AGENT, Role.SUPERVISOR}),
    # tenant_admin is intentionally absent: administration does not imply customer access.
}

CONTACT_FIELDS = frozenset({"email", "phone", "address"})

# Which customer fields each role may change. Supervisor `policy_note` is approved in
# the matrix but not yet enabled (Session 4 scope: contact fields only).
_UPDATABLE_FIELDS: dict[Role, frozenset[str]] = {
    Role.SUPPORT_AGENT: CONTACT_FIELDS,
    Role.SUPERVISOR: CONTACT_FIELDS,
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str  # stable reason code for audit logs, e.g. "role_not_permitted"


ALLOW = Decision(True, "allowed")


def authorize(role: Role, action: Action, fields: frozenset[str] = frozenset()) -> Decision:
    """Decide whether ``role`` may perform ``action`` (touching ``fields`` for updates)."""
    if role not in _ALLOWED_ROLES.get(action, frozenset()):
        return Decision(False, "role_not_permitted")
    if action is Action.UPDATE_CUSTOMER:
        if not fields:
            return Decision(False, "no_fields")
        if not fields <= _UPDATABLE_FIELDS.get(role, frozenset()):
            return Decision(False, "field_not_permitted")
    return ALLOW
