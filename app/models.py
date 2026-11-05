"""Domain models for the lab's synthetic data.

Every tenant-owned entity carries a required ``tenant_id``. Models reject unknown
fields (``extra="forbid"``) so unexpected input - for example a stray ``role`` or
``tenant_id`` smuggled into a payload - is an error rather than silently ignored.

These models describe data shape only. They do not perform authorisation.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# Stable, human-readable identifiers, e.g. "northstar", "ns-cust-001".
ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class Role(str, Enum):
    SUPPORT_AGENT = "support_agent"
    SUPERVISOR = "supervisor"
    TENANT_ADMIN = "tenant_admin"


class PolicyType(str, Enum):
    MOTOR = "motor"
    HOME = "home"
    TRAVEL = "travel"


class TicketStatus(str, Enum):
    OPEN = "open"
    PENDING = "pending"
    CLOSED = "closed"


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Tenant(_Record):
    tenant_id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)


class User(_Record):
    user_id: str = Field(pattern=ID_PATTERN)
    tenant_id: str = Field(pattern=ID_PATTERN)
    display_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    role: Role


class Customer(_Record):
    customer_id: str = Field(pattern=ID_PATTERN)
    tenant_id: str = Field(pattern=ID_PATTERN)
    full_name: str = Field(min_length=1)
    # Contact fields: the only fields a support_agent may update (architecture.md §7).
    email: str = Field(min_length=3)
    phone: str = Field(min_length=1)
    address: str = Field(min_length=1)
    # Policy fields: supervisor-only updates (policy_note); policy_number/type read-only.
    policy_number: str = Field(min_length=1)
    policy_type: PolicyType
    policy_note: str = ""


class Ticket(_Record):
    ticket_id: str = Field(pattern=ID_PATTERN)
    tenant_id: str = Field(pattern=ID_PATTERN)
    customer_id: str = Field(pattern=ID_PATTERN)
    assigned_to: str = Field(pattern=ID_PATTERN)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)  # Untrusted customer-supplied text.
    status: TicketStatus


class KnowledgeDocument(_Record):
    doc_id: str = Field(pattern=ID_PATTERN)
    tenant_id: str = Field(pattern=ID_PATTERN)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)  # Untrusted content: data, never instructions.
