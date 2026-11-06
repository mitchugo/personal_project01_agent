import { render, screen, waitFor, within } from "@testing-library/react";
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
  it("lists specs as prepared/not executed and loads nothing paid", async () => {
    const spec = (id: string) => ({
      id, title: `Title ${id}`, objective: "obj", asset: "asset", entry_point: "entry", threat_ids: ["T-01"],
      expected: "expected", status: "prepared", evidence_runs: [], markdown: `# ${id}\n<script>x</script>`,
    });
    const { calls } = mockApi({
      "/demo/evidence": () => json({ specs: ["A01", "A02"].map(spec), evidence: [] }),
    });
    render(<Evidence />);
    await waitFor(() => expect(screen.getAllByText("Prepared — not executed").length).toBeGreaterThanOrEqual(2));
    expect(screen.getByText("Before / after comparison")).toBeInTheDocument();
    expect(calls.map((c) => c.url)).toEqual(["/api/demo/evidence"]);
    expect(document.querySelector("script")).toBeNull();
  });
});
