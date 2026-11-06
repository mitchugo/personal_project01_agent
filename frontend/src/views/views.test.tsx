import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { FixtureUser, InspectorEvent } from "../api/types";
import { CONFIG, headerOf, json, mockApi } from "../test/fixtures";
import { Approvals } from "./Approvals";
import { Evidence } from "./Evidence";
import { Inspector, describeEvent } from "./Inspector";

const AGENT = CONFIG.users[0] as FixtureUser;
const SUPER = CONFIG.users[1] as FixtureUser;

const REFUND = {
  refund_id: "refund-0123456789abcdef0123456789abcdef",
  customer_id: "ns-cust-003",
  requested_by: "ns-agent-01",
  amount_pence: 4250,
  currency: "GBP",
  reason: '<img src=x onerror="window.__pwned=true"> **please**',
  status: "pending_approval",
  approved_by: null,
  created_at: "2026-11-05T10:00:00+00:00",
  approved_at: null,
  executed_at: null,
};

const ev = (event_type: string, metadata: Record<string, string | number | boolean>, outcome = "success"): InspectorEvent => ({
  event_type, correlation_id: "cid-1", timestamp: "2026-11-05T10:00:01Z", outcome,
  actor_user_id: "ns-agent-01", tenant_id: "northstar", metadata,
});

describe("Security Inspector", () => {
  it("keeps model proposals, backend decisions and outcomes as separate rows", async () => {
    mockApi({
      "/demo/inspector": () => json({
        source: "in-memory sanitised audit buffer", tenant_id: "northstar",
        groups: [{ correlation_id: "cid-1", events: [
          ev("tool.invoke", { tool: "read_customer", decision: "deny", reason: "not_found_in_tenant", resource_id: "mc-cust-001" }, "denied"),
          ev("agent.tool_proposal", { proposed_tool: "read_customer", tool_status: "not_found", iteration: 1 }, "denied"),
          ev("tool.invoke", { tool: "unknown", decision: "deny", reason: "unknown_tool" }, "rejected"),
          ev("agent.tool_proposal", { proposed_tool: "unregistered", tool_status: "invalid", iteration: 1 }, "rejected"),
        ] }],
      }),
    });
    render(<Inspector user={AGENT} focusCorrelationId={null} onClearFocus={() => {}} />);
    expect(await screen.findByText("cid-1")).toBeInTheDocument();
    expect(screen.getAllByText("Model proposed")).toHaveLength(2);
    expect(screen.getAllByText("Backend decision")).toHaveLength(2);
    const tones = [...document.querySelectorAll("[data-tone]")].map((el) => el.getAttribute("data-tone"));
    expect(tones).toEqual(["denied", "proposed", "denied", "proposed"]);
  });

  it("maps refund approval and execution events to allowed / executed", () => {
    expect(describeEvent(ev("refund.approval", { from_status: "pending_approval", to_status: "approved" })).tone).toBe("allowed");
    expect(describeEvent(ev("refund.execution", { from_status: "approved", to_status: "executed" })).tone).toBe("executed");
    expect(describeEvent(ev("refund.approval", { reason: "self_approval" }, "denied")).tone).toBe("denied");
  });

  it("shows an honest empty state rather than fabricated events", async () => {
    mockApi({ "/demo/inspector": () => json({ source: "x", tenant_id: "northstar", groups: [] }) });
    render(<Inspector user={AGENT} focusCorrelationId={null} onClearFocus={() => {}} />);
    expect(await screen.findByText(/No events recorded for this tenant/)).toBeInTheDocument();
  });
});

describe("Approvals", () => {
  it("sends exactly the stored binding values and the fixture header, then shows the backend decision", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      "/demo/refunds/": () => json({ action: "approve_refund", status: "denied", reason: "role_not_permitted" }, 403),
      "/demo/refunds": () => json({ tenant_id: "northstar", refunds: [REFUND], reject_supported: false }),
    });
    render(<Approvals user={AGENT} />);
    await user.click(await screen.findByRole("button", { name: "Approve…" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("ns-cust-003")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Send approval to backend" }));

    expect(await screen.findByText(/not permitted to do this/)).toBeInTheDocument();
    const approve = calls.find((c) => c.url.endsWith("/approve"))!;
    expect(JSON.parse(approve.init.body as string)).toEqual({ customer_id: "ns-cust-003", amount_pence: 4250, currency: "GBP" });
    expect(headerOf(approve.init, "X-Dev-User-Id")).toBe("ns-agent-01");
    expect(document.querySelector("[data-tone='denied']")).not.toBeNull();
  });

  it("offers no working reject action and renders untrusted reason text inertly", async () => {
    mockApi({ "/demo/refunds": () => json({ tenant_id: "northstar", refunds: [REFUND], reject_supported: false }) });
    render(<Approvals user={SUPER} />);
    expect(await screen.findByRole("button", { name: "Reject (not implemented)" })).toBeDisabled();
    expect(screen.getByText(/onerror/)).toBeInTheDocument();         // shown as text
    expect(document.querySelector("img")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it("shows the backend's refusal when a role cannot view the queue", async () => {
    mockApi({ "/demo/refunds": () => json({ error: { code: "forbidden", message: "Not permitted for this role.", correlation_id: "c" } }, 403) });
    render(<Approvals user={{ ...SUPER, user_id: "ns-admin-01", role: "tenant_admin" }} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not permitted");
  });
});

describe("Attack evidence", () => {
  const spec = (id: string) => ({
    id, title: `Title ${id}`, objective: "obj", asset: "asset", entry_point: "entry", threat_ids: ["T-01"],
    expected: "expected", status: "prepared", evidence_runs: [], markdown: `# ${id}\n<script>x</script>`,
  });
  const HOSTILE = '<img src=x onerror="window.__pwned=true"><script>window.__pwned=true</script>';
  const result = (spec_id: string, status: string, live: Partial<Record<string, unknown>> = {}, mockTrials = 0) => ({
    spec_id, status, categories: ["cat"], entry_points: ["kb_document"], dataset_threats: ["T-03"], dataset_cases: [`${spec_id}-X1`],
    live: {
      trials: 0, conclusive: 0, inconclusive: 0, cases: [], configured_models: [], actual_models: [], model_mismatches: 0,
      objective_successes: 0, objective_success_ci95: null, backend_bypasses: 0, backend_denials: 0, model_compliance: 0,
      refused: 0, errored: 0, evidence_incomplete: 0, outcomes: {}, runs: [], ...live,
    },
    mock: { trials: mockTrials, by_behaviour: {}, runs: mockTrials ? ["s9-mock-obedient"] : [] },
    notes: { model_behaviour: HOSTILE, backend: "backend note", impact: "impact note" },
    limitations: [HOSTILE],
  });
  const LIVE = { trials: 6, conclusive: 6, cases: ["A01-X1"], configured_models: ["claude-sonnet-5-5"],
    actual_models: ["claude-sonnet-5-5"], objective_success_ci95: [0, 0.39], backend_denials: 2, runs: ["s10-live-a01"] };
  const OVERVIEW = {
    schema: "assessment-view/v1", scope: "Offline aggregate results.",
    runs: [{ run_id: "s10-live-a01", session: 10, mode: "live", behaviour: null, available: true, git_commit: "682eab4",
      git_dirty: false, dataset_version: "1.1.0", invalid_records: 0, trials: 2 },
    { run_id: "s9-mock-obedient", session: 9, mode: "mock", behaviour: "obedient", available: true, git_commit: "02df3c2",
      git_dirty: true, dataset_version: "1.0.0", invalid_records: 0, trials: 1 }],
    specs: [result("A01", "tested_live", LIVE, 4), result("A02", "tested_mock", {}, 4), result("A03", "prepared"),
      result("A04", "inconclusive", { trials: 3, inconclusive: 3, evidence_incomplete: 3, runs: ["s10-live-a04"] })],
    totals: { live_attack_trials: 9, live_objective_successes: 0, live_backend_bypasses: 0, live_benign_trials: 5,
      live_benign_completed: 5, live_model_calls: 62, live_cost_usd: 0.349024, live_models: ["claude-sonnet-5-5"], invalid_records: 0 },
    findings: [{ id: "F-002", title: HOSTILE, type: "finding", severity: "Provisional Medium", status: "Open (draft)",
      reproduction_mock: "Reproduced (mock)", reproduction_live: "Not reproduced (0/9)", exploited_live: false,
      affected_specs: ["A01"], threats: ["T-22"], remediation: "fix", retest_status: "Not retested", evidence_ref: "findings/F-002.md" }],
    comparisons: [],
  };
  const TRIAL = (id: string, outcome: string, complete = true) => ({
    trial_id: id, test_id: id.split("#")[0], kind: "attack", mode: "live", outcome, spec_id: "A01",
    timestamp_utc: "2026-11-06T12:00:00+00:00", status: "completed", configured_model: "claude-sonnet-5-5",
    actual_models: ["claude-sonnet-5-5"], model_mismatch: false, principal: "ns-agent-01", tenant: "northstar",
    entry_point: "kb_document", delivered: true, complied: false, compliant_proposal_blocked: false, compliant_proposal_executed: false,
    turns: [{ correlation_id: "11111111-2222-3333-4444-555555555555", principal: "ns-agent-01", tenant: "northstar", http_status: 200,
      termination: "completed", proposed_tools: ["search_kb"], decisions: [{ event: "tool.invoke", outcome: "success", decision: "allow",
        reason: "allowed", tool: "search_kb", resource_id: null }], actions: [{ tool: "search_kb", status: "ok", detail: null }],
      model_calls: [{ iteration: 1, model: "claude-sonnet-5-5", input_tokens: 2000, output_tokens: 80, cost_usd: 0.0048, stop_reason: "tool_use", refusal_category: null }] }],
    db_changes: {}, usage: { model_calls: 2, input_tokens: 4000, output_tokens: 160, cost_usd: 0.011312, cost_basis: "estimated" },
    duration_ms: 5200, evidence_complete: complete,
  });

  function routes() {
    return mockApi({
      "/demo/assessment/trials": () => json({ run_id: "s10-live-a01", session: 10, mode: "live", behaviour: null, git_commit: "682eab4",
        git_dirty: false, dataset_version: "1.1.0", invalid_records: 0,
        trials: [TRIAL("A01-X1#1", "DELIVERED_NOT_ACHIEVED"), TRIAL("A01-X1#2", "INCONCLUSIVE", false)] }),
      "/demo/assessment": () => json(OVERVIEW),
      "/demo/evidence": () => json({ specs: ["A01", "A02", "A03", "A04"].map(spec), evidence: [] }),
    });
  }

  it("shows real counts and distinguishes live, mock, prepared and inconclusive", async () => {
    const { calls } = routes();
    render(<Evidence />);
    const table = await screen.findByRole("table", { name: "Attack overview" });
    const statuses = [...table.querySelectorAll("[data-status]")].map((el) => el.getAttribute("data-status"));
    expect(statuses).toEqual(["tested_live", "tested_mock", "prepared", "inconclusive"]);
    expect(within(table).getByText("Tested with mock provider")).toBeInTheDocument();
    expect(within(table).getByText("Inconclusive")).toBeInTheDocument();
    expect(screen.getByTestId("success-A01")).toHaveTextContent("0/6");
    expect(screen.getByTestId("success-A02")).toHaveTextContent("—");       // mock-only: no live success figure
    expect(screen.getByText("0/9")).toBeInTheDocument();                       // totals strip
    expect(calls.map((c) => c.url).sort()).toEqual(["/api/demo/assessment", "/api/demo/evidence"]);
    expect(calls.some((c) => c.url.includes("/chat"))).toBe(false);
  });

  it("never claims a successful attack or live exploitation that the data does not contain", async () => {
    routes();
    render(<Evidence />);
    await screen.findByRole("table", { name: "Attack overview" });
    expect(screen.queryByText(/Unintended impact within permissions/)).toBeNull();
    expect(screen.queryByText(/Backend control bypassed/)).toBeNull();
    expect(screen.getByTestId("exploited-F-002")).toHaveTextContent("No");
    expect(screen.getByText(/Provisional Medium/)).toBeInTheDocument();
    expect(screen.getByText(/No remediation results exist yet/)).toBeInTheDocument();
  });

  it("renders attacker-controlled evidence text inertly", async () => {
    routes();
    render(<Evidence />);
    await screen.findByRole("table", { name: "Attack overview" });
    expect(screen.getAllByText(/onerror/).length).toBeGreaterThan(0);       // shown as text
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it("explores trials of a selected run and flags incomplete evidence", async () => {
    const user = userEvent.setup();
    const { calls } = routes();
    render(<Evidence />);
    await screen.findByRole("table", { name: "Attack overview" });
    await user.click(within(screen.getByRole("group", { name: "Assessment runs" })).getByRole("button", { name: /S10 live · A01/ }));
    expect(await screen.findAllByTestId("trial")).toHaveLength(2);
    expect(calls.some((c) => c.url === "/api/demo/assessment/trials?run_id=s10-live-a01")).toBe(true);
    expect(screen.getByText("Evidence incomplete")).toBeInTheDocument();
    expect(screen.getByText("Inconclusive (missing evidence)")).toBeInTheDocument();
    expect(screen.getAllByText(/11111111-2222-3333-4444-555555555555/)).toHaveLength(2);   // one per trial
  });

  const SUMMARY = {
    scope: "Local synthetic lab only.", assessment_period: "5-6 November 2026", remediation_status: "not_started",
    residual_risks: [`F-003 open. ${HOSTILE}`],
    report_links: [{ id: "reports/pre-remediation/executive-summary.md", label: "Executive summary" }],
    controls_exercised: { proposals: 100, not_executed: 36, requests_rejected_before_model: 3, trials_without_tool_call: 24,
      refusals: [{ tool: "read_customer", status: "not_found", count: 18 }] },
  };
  const withSummary = (summary: unknown, findings: unknown[] = OVERVIEW.findings) => ({ ...OVERVIEW, summary, findings });

  it("shows the assessment overview with remediation not started and computed control counts", async () => {
    mockApi({
      "/demo/assessment": () => json(withSummary(SUMMARY, [
        { ...OVERVIEW.findings[0], classification: "confirmed_mock_only" },
        { ...OVERVIEW.findings[0], id: "F-003", severity: "Medium", exploited_live: true, classification: "confirmed_live" }])),
      "/demo/evidence": () => json({ specs: [], evidence: [] }),
    });
    render(<Evidence />);
    const panel = await screen.findByTestId("assessment-overview");
    expect(within(panel).getByTestId("remediation-status")).toHaveTextContent("Remediation: Not started");
    expect(within(panel).getByTestId("not-executed")).toHaveTextContent("36 of 100");
    expect(within(panel).getByText(/read_customer · not_found ×18/)).toBeInTheDocument();
    expect(within(panel).getByText(/24 attack trials made no tool call/)).toBeInTheDocument();
    expect(within(panel).getByTestId("classification-F-002")).toHaveTextContent("not reproduced live");
    expect(within(panel).getByTestId("classification-F-003")).toHaveTextContent("Confirmed live (synthetic lab)");
    expect(within(panel).queryByText(/Retested|Remediated|Fixed/)).toBeNull();
    expect(document.querySelector("img")).toBeNull();                         // residual-risk text rendered inertly
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it("never implies remediation when the status is missing, and opens report links by ID only", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      "/demo/evidence/file": () => json({ id: "reports/pre-remediation/executive-summary.md", name: "executive-summary.md",
        content: "# Executive Summary" }),
      "/demo/assessment": () => json(withSummary({ ...SUMMARY, remediation_status: null })),
      "/demo/evidence": () => json({ specs: [], evidence: [] }),
    });
    render(<Evidence />);
    const panel = await screen.findByTestId("assessment-overview");
    expect(within(panel).getByTestId("remediation-status")).toHaveTextContent("Remediation: Unknown");
    await user.click(within(panel).getByRole("button", { name: "Executive summary" }));
    expect(await screen.findByRole("heading", { name: "Executive Summary" })).toBeInTheDocument();
    expect(calls.some((c) => c.url === "/api/demo/evidence/file?id=reports%2Fpre-remediation%2Fexecutive-summary.md")).toBe(true);
  });

  it("omits the overview panel when the server provides no summary", async () => {
    routes();
    render(<Evidence />);
    await screen.findByRole("table", { name: "Attack overview" });
    expect(screen.queryByTestId("assessment-overview")).toBeNull();
  });

  it("shows mock-only specs with a mock caveat and no live model", async () => {
    const user = userEvent.setup();
    routes();
    render(<Evidence />);
    const table = await screen.findByRole("table", { name: "Attack overview" });
    await user.click(within(table).getByRole("button", { name: /A02/ }));
    expect(await screen.findByText(/Mock provider only: shows backend behaviour/)).toBeInTheDocument();
    expect(screen.getAllByText("Not tested live").length).toBeGreaterThan(0);
  });
});
