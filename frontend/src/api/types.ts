// Shapes returned by the FastAPI backend. The UI never sends role, tenant or approver:
// identity is only the X-Dev-User-Id fixture selector, resolved server-side.

export type Role = "support_agent" | "supervisor" | "tenant_admin";

export interface FixtureUser {
  user_id: string;
  display_name: string;
  role: Role;
  tenant_id: string;
  tenant_name: string;
}

export interface DemoConfig {
  identity_notice: string;
  users: FixtureUser[];
  agent: {
    enabled: boolean;
    provider: string | null;
    configured_model: string | null;
    fallback: string;
  };
}

export interface ActionRecord {
  tool: string;
  status: string; // ok | denied | not_found | invalid | conflict | skipped | error
  detail?: string | null;
}

export interface ChatResponse {
  correlation_id: string;
  reply: string;
  agent_connected: boolean;
  acting_as: { user_id: string; tenant_id: string; role: Role; identity_source: string };
  actions?: ActionRecord[];
  termination?: string;
}

export interface InspectorEvent {
  event_type: string;
  correlation_id: string | null;
  timestamp: string | null;
  outcome: string | null;
  actor_user_id: string | null;
  tenant_id: string | null;
  metadata: Record<string, string | number | boolean>;
}

export interface InspectorResponse {
  source: string;
  tenant_id: string;
  groups: { correlation_id: string; events: InspectorEvent[] }[];
}

export interface Refund {
  refund_id: string;
  customer_id: string;
  requested_by: string;
  amount_pence: number;
  currency: "GBP";
  reason: string;
  status: "pending_approval" | "approved" | "executed";
  approved_by: string | null;
  created_at: string;
  approved_at: string | null;
  executed_at: string | null;
}

export interface RefundsResponse {
  tenant_id: string;
  refunds: Refund[];
  reject_supported: boolean;
}

export interface ServiceResult {
  action: "approve_refund" | "execute_refund";
  status: "ok" | "denied" | "not_found" | "conflict";
  reason: string;
  data?: Record<string, unknown> | null;
}

export interface AttackSpec {
  id: string;
  title: string;
  objective: string | null;
  asset: string | null;
  entry_point: string | null;
  threat_ids: string[];
  expected: string | null;
  status: "prepared" | "executed";
  evidence_runs: string[];
  markdown: string;
}

export interface EvidenceIndex {
  specs: AttackSpec[];
  evidence: { group: string; files: { id: string; name: string; bytes: number }[] }[];
}

export interface EvidenceFile {
  id: string;
  name: string;
  content: string;
}

// --- Offline red-team assessment (GET /demo/assessment) -------------------------------------
// Aggregate results from the synthetic lab's harness. Not tenant activity.

export type AssessmentStatus = "prepared" | "tested_mock" | "tested_live" | "partially_tested" | "inconclusive";

export interface AssessmentRun {
  run_id: string;
  session: number;
  mode: "mock" | "live";
  behaviour: string | null;
  available: boolean;
  git_commit: string | null;
  git_dirty: boolean | null;
  dataset_version: string | null;
  invalid_records: number;
  trials: number;
}

export interface SpecAssessment {
  spec_id: string;
  status: AssessmentStatus;
  categories: string[];
  entry_points: string[];
  dataset_threats: string[];
  dataset_cases: string[];
  live: {
    trials: number;
    conclusive: number;
    inconclusive: number;
    cases: string[];
    configured_models: string[];
    actual_models: string[];
    model_mismatches: number;
    objective_successes: number;
    objective_success_ci95: [number, number] | null;
    backend_bypasses: number;
    backend_denials: number;
    model_compliance: number;
    refused: number;
    errored: number;
    evidence_incomplete: number;
    outcomes: Record<string, number>;
    runs: string[];
  };
  mock: { trials: number; by_behaviour: Record<string, { trials: number; outcomes: Record<string, number> }>; runs: string[] };
  notes: { model_behaviour: string | null; backend: string | null; impact: string | null };
  limitations: string[];
}

export interface Finding {
  id: string;
  title: string | null;
  type: "finding" | "observation" | null;
  severity: string | null;
  status: string | null;
  reproduction_mock: string | null;
  reproduction_live: string | null;
  exploited_live: boolean;
  affected_specs: string[];
  threats: string[];
  remediation: string | null;
  retest_status: string | null;
  evidence_ref: string | null;
}

export interface AssessmentOverview {
  schema: string;
  scope: string;
  runs: AssessmentRun[];
  specs: SpecAssessment[];
  totals: {
    live_attack_trials: number;
    live_objective_successes: number;
    live_backend_bypasses: number;
    live_benign_trials: number;
    live_benign_completed: number;
    live_model_calls: number;
    live_cost_usd: number;
    live_models: string[];
    invalid_records: number;
  };
  findings: Finding[];
  comparisons: unknown[];
}

export interface TrialTurn {
  correlation_id: string | null;
  principal: string | null;
  tenant: string | null;
  http_status: number | null;
  termination: string | null;
  proposed_tools: string[];
  decisions: { event: string; outcome: string | null; decision: string | null; reason: string | null; tool: string | null; resource_id: string | null }[];
  actions: { tool: string; status: string | null; detail: string | null }[];
  model_calls: { iteration: number | null; model: string | null; input_tokens: number | null; output_tokens: number | null; cost_usd: number | null; stop_reason: string | null; refusal_category: string | null }[];
}

export interface TrialRecord {
  trial_id: string;
  test_id: string;
  kind: "attack" | "benign";
  mode: "mock" | "live";
  outcome: string;
  spec_id: string | null;
  timestamp_utc: string | null;
  status: string | null;
  configured_model: string | null;
  actual_models: string[];
  model_mismatch: boolean | null;
  principal: string | null;
  tenant: string | null;
  entry_point: string | null;
  delivered: boolean | null;
  complied: boolean | null;
  compliant_proposal_blocked: boolean | null;
  compliant_proposal_executed: boolean | null;
  turns: TrialTurn[];
  db_changes: Record<string, { added: number; changed: number }>;
  usage: { model_calls: number | null; input_tokens: number | null; output_tokens: number | null; cost_usd: number | null; cost_basis: "simulated" | "estimated" | null };
  duration_ms: number | null;
  evidence_complete: boolean;
}

export interface RunTrials {
  run_id: string;
  session: number;
  mode: "mock" | "live";
  behaviour: string | null;
  git_commit: string | null;
  git_dirty: boolean | null;
  dataset_version: string | null;
  invalid_records: number;
  trials: TrialRecord[];
}
