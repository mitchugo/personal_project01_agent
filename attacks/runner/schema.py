"""Dataset schema and loader for attack and benign test cases.

Every case is validated strictly (unknown keys rejected) before anything runs. A case
describes WHAT is attacked and HOW success is judged. It never contains secrets or
real personal data: payloads are synthetic, and each one carries a canary token so that
delivery to the model can be checked mechanically.
"""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app import fixtures

DATASET_DIR = Path(__file__).resolve().parents[1] / "datasets"
MANIFEST = DATASET_DIR / "manifest.json"

FIXTURE_USERS = frozenset(u.user_id for u in fixtures.USERS)
CASE_ID = r"^(A0[1-8]|B[0-9]{2})-[A-Z0-9]{2,6}$"
CANARY = r"^CANARY-[A-Z0-9-]{4,40}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- setup steps: applied directly to the disposable DB before the trial (never via the agent) ---

class PlantKbDocument(Strict):
    action: Literal["plant_kb_document"]
    doc_id: str = Field(pattern=r"^(ns|mc)-kb-9[0-9]{2}$")   # 9xx range: never collides with fixtures
    tenant_id: Literal["northstar", "meridian"]
    title: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=10, max_length=2000)


class SetCustomerField(Strict):
    action: Literal["set_customer_field"]
    customer_id: str = Field(pattern=r"^(ns|mc)-cust-[0-9]{3}$")
    field: Literal["email", "phone", "address"]
    value: str = Field(min_length=3, max_length=200)


class CreatePendingRefund(Strict):
    action: Literal["create_pending_refund"]
    requested_by: str
    customer_id: str = Field(pattern=r"^(ns|mc)-cust-[0-9]{3}$")
    amount_pence: int = Field(ge=1, le=50_000)
    reason: str = Field(min_length=10, max_length=200)


SetupStep = Annotated[Union[PlantKbDocument, SetCustomerField, CreatePendingRefund], Field(discriminator="action")]


# --- scripted (mock) model behaviour --------------------------------------------------

class MockToolCall(Strict):
    name: str = Field(min_length=1, max_length=64)
    input: object


class MockTurn(Strict):
    text: str = ""
    tool_calls: list[MockToolCall] = Field(default_factory=list, max_length=6)
    model: str | None = None            # served model; None = the configured model
    stop_reason: str | None = None      # None = tool_use if tool_calls else end_turn
    error: Literal["timeout", "rate_limited", "unavailable"] | None = None


# --- conversation turns -----------------------------------------------------------------

class ChatTurn(Strict):
    principal: str                       # X-Dev-User-Id for this request
    message: str = Field(min_length=1, max_length=4000)
    extra_headers: dict[str, str] = Field(default_factory=dict)
    extra_body: dict[str, object] = Field(default_factory=dict)
    mock: dict[str, list[MockTurn]] = Field(default_factory=dict)   # behaviour name -> model turns


# --- grading inputs: deterministic conditions over evidence ------------------------------

class Condition(Strict):
    """One deterministic check over DB diff, backend actions or captured model input.

    type:
      customer_field_equals      customer_id, field, value
      customer_changed           customer_id
      any_customer_changed_in_tenant  tenant_id
      refund_status_in           statuses
      refund_created             (any new refund row)
      refunds_created_at_least   n
      ledger_rows_at_least       n
      draft_body_contains        text
      draft_recipient_mismatch   (stored draft recipient != customer's stored email: backend invariant)
      draft_recipient_changed    (draft goes to an address other than the pre-trial email: impact)
      draft_created
      cross_tenant_change        (any changed/added row whose tenant differs from the acting principal's)
      model_input_contains_other_tenant_data
      response_contains          text   (HTTP response body, not model intent)
      acting_as_mismatch         (response acting_as differs from the DB identity of X-Dev-User-Id)
      backend_action_ok          tool   (backend executed this tool with status ok)
    """

    type: Literal[
        "customer_field_equals", "customer_changed", "any_customer_changed_in_tenant",
        "refund_status_in", "refund_created", "refunds_created_at_least", "ledger_rows_at_least",
        "draft_body_contains", "draft_recipient_mismatch", "draft_recipient_changed", "draft_created",
        "cross_tenant_change", "model_input_contains_other_tenant_data",
        "response_contains", "acting_as_mismatch", "backend_action_ok",
    ]
    customer_id: str | None = None
    tenant_id: str | None = None
    field: str | None = None
    value: str | None = None
    statuses: list[str] | None = None
    n: int | None = None
    text: str | None = None
    tool: str | None = None


class Indicator(Strict):
    """Model-behaviour signal: the model did what the attacker asked (proposal level, not impact)."""

    type: Literal["proposed_tool", "proposed_tool_arg", "reply_contains", "reply_contains_canary"]
    tool: str | None = None
    arg: str | None = None
    value: str | None = None
    text: str | None = None


class CaseSpec(Strict):
    id: str = Field(pattern=CASE_ID)
    kind: Literal["attack", "benign"]
    spec_id: str | None = Field(default=None, pattern=r"^A0[1-8]$")
    threat_refs: list[str] = Field(default_factory=list)
    category: Literal[
        "indirect_injection", "cross_tenant", "recipient_manipulation", "identity_spoofing",
        "approval_bypass", "session_contamination", "disclosure", "exfiltration", "benign",
    ]
    objective: str = Field(min_length=10, max_length=400)
    entry_point: Literal[
        "chat_message", "kb_document", "ticket_text", "customer_field", "http_header",
        "request_body", "tool_arguments",
    ]
    canary: str | None = Field(default=None, pattern=CANARY)
    delivery: Literal["model_input_contains_canary", "request_processed"] = "model_input_contains_canary"
    setup: list[SetupStep] = Field(default_factory=list)
    turns: list[ChatTurn] = Field(min_length=1, max_length=5)
    expected_secure_behaviour: str = Field(min_length=10)
    expected_business_outcome: str = Field(min_length=5)
    expected_backend_decision: Literal["deny", "allow_within_permissions", "no_action", "allow"]
    compliance_indicators: list[Indicator] = Field(default_factory=list)
    success_conditions: list[Condition] = Field(default_factory=list)   # attacker objective realised (impact)
    bypass_conditions: list[Condition] = Field(default_factory=list)    # a backend control was violated
    completion_conditions: list[Condition] = Field(default_factory=list)  # benign task done
    evidence_requirements: list[Literal["audit_chain", "db_diff", "model_identity", "proposals",
                                        "delivery_check", "isolation_check"]] = Field(min_length=1)
    cleanup: str = "Disposable database deleted after the trial; nothing persists."
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self):
        for turn in self.turns:
            if turn.principal not in FIXTURE_USERS:
                raise ValueError(f"unknown fixture principal {turn.principal!r}")
        for step in self.setup:
            if isinstance(step, CreatePendingRefund) and step.requested_by not in FIXTURE_USERS:
                raise ValueError("unknown requested_by")
        if self.kind == "attack":
            if not self.spec_id or not self.canary:
                raise ValueError("attack cases need spec_id and canary")
            if not (self.success_conditions or self.bypass_conditions):
                raise ValueError("attack cases need success or bypass conditions")
            if self.canary not in json.dumps(self.model_dump(include={"setup", "turns"})):
                raise ValueError("canary must appear in the payload (setup or turns)")
        else:
            if self.spec_id is not None or self.category != "benign":
                raise ValueError("benign cases have no spec_id and category 'benign'")
            if not self.completion_conditions:
                raise ValueError("benign cases need completion conditions")
        return self

    @property
    def principal(self) -> str:
        return self.turns[0].principal

    def payload_sha256(self) -> str:
        return sha256_json(self.model_dump(include={"setup", "turns"}, mode="json"))


class Dataset(Strict):
    version: str
    sha256: dict[str, str]
    cases: list[CaseSpec]

    def get(self, case_id: str) -> CaseSpec:
        for case in self.cases:
            if case.id == case_id:
                return case
        raise UnknownCaseError(case_id)


class DatasetError(Exception):
    pass


class UnknownCaseError(DatasetError):
    def __init__(self, case_id: str):
        super().__init__(f"unknown test case id: {case_id!r}")


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _load_jsonl(path: Path) -> list[CaseSpec]:
    cases = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(CaseSpec.model_validate_json(line))
        except ValidationError as exc:
            raise DatasetError(f"{path.name}:{number}: invalid case: {exc.errors()[0]['msg']}") from None
    return cases


def load_dataset(manifest_path: Path = MANIFEST) -> Dataset:
    """Load every file listed in the manifest. Fails closed on any invalid or duplicate case."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases: list[CaseSpec] = []
    hashes = {}
    for name in manifest["files"]:
        path = manifest_path.parent / name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        cases.extend(_load_jsonl(path))
    ids = [c.id for c in cases]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise DatasetError(f"duplicate case ids: {duplicates}")
    return Dataset(version=manifest["version"], sha256=hashes, cases=cases)


def select(dataset: Dataset, ids: list[str] | None = None, category: str | None = None,
           kind: str | None = None) -> list[CaseSpec]:
    if ids:
        return [dataset.get(i) for i in ids]   # unknown ids raise
    chosen = [c for c in dataset.cases
              if (category is None or c.category == category) and (kind is None or c.kind == kind)]
    if not chosen:
        raise DatasetError("selection matched no cases")
    return chosen
