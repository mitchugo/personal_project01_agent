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
