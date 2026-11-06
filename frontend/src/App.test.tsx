import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { CONFIG, headerOf, json, mockApi } from "./test/fixtures";

const CHAT_OK = {
  correlation_id: "11111111-2222-4333-8444-555555555555",
  reply: "The phone number on file is **07700 900002**.",
  agent_connected: true,
  acting_as: { user_id: "ns-agent-01", tenant_id: "northstar", role: "support_agent", identity_source: "local-fixture" },
  termination: "completed",
  actions: [
    { tool: "read_customer", status: "ok" },
    { tool: "request_refund", status: "ok", detail: "pending_approval" },
    { tool: "read_customer", status: "not_found" },
    { tool: "unregistered", status: "invalid" },
    { tool: "search_kb", status: "skipped" },
  ],
};

async function selectUser(user: ReturnType<typeof userEvent.setup>, id = "ns-agent-01") {
  await waitFor(() => expect(screen.getByLabelText("Development user")).not.toBeDisabled());
  await user.selectOptions(screen.getByLabelText("Development user"), id);
}

describe("app shell", () => {
  it("renders navigation, the dev-identity warning and the configured model", async () => {
    mockApi({ "/demo/config": () => json(CONFIG) });
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const label of ["Workspace", "Security Inspector", "Approvals", "Attack Evidence"]) {
      expect(within(nav).getByRole("button", { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(screen.getByText(/Dev fixture identity — not authentication/)).toBeInTheDocument();
    expect(await screen.findByText("claude-sonnet-5-5")).toBeInTheDocument();
    expect(screen.getByText(/each message makes a real, paid model call/i)).toBeInTheDocument();
  });

  it("does not call /chat or any paid endpoint on page load", async () => {
    const { calls } = mockApi({ "/demo/config": () => json(CONFIG) });
    render(<App />);
    await screen.findByText("claude-sonnet-5-5");
    expect(calls.map((c) => c.url)).toEqual(["/api/demo/config"]);
  });

  it("shows when the agent is off instead of pretending it is connected", async () => {
    mockApi({ "/demo/config": () => json({ ...CONFIG, agent: { ...CONFIG.agent, enabled: false, configured_model: null } }) });
    render(<App />);
    expect(await screen.findByText("Agent off (fixed reply)")).toBeInTheDocument();
  });
});

describe("identity selection", () => {
  it("updates the header and sends only X-Dev-User-Id (never role or tenant)", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({ "/demo/config": () => json(CONFIG), "/chat": () => json(CHAT_OK) });
    render(<App />);
    await selectUser(user, "mc-agent-01");
    expect(screen.getByTestId("header-tenant")).toHaveTextContent("Meridian Cover");

    await user.type(screen.getByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText(/07700 900002/);

    const chat = calls.find((c) => c.url === "/api/chat")!;
    expect(headerOf(chat.init, "X-Dev-User-Id")).toBe("mc-agent-01");
    expect(JSON.parse(chat.init.body as string)).toEqual({ message: "hello" });
    expect(Object.keys(chat.init.headers as object)).not.toEqual(expect.arrayContaining(["X-Role", "X-Tenant-Id"]));
    expect(chat.init.credentials).toBe("omit");
  });

  it("clears the conversation when the identity changes", async () => {
    const user = userEvent.setup();
    mockApi({ "/demo/config": () => json(CONFIG), "/chat": () => json(CHAT_OK) });
    render(<App />);
    await selectUser(user);
    await user.type(screen.getByLabelText("Message"), "first identity message");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("first identity message");
    await user.selectOptions(screen.getByLabelText("Development user"), "ns-super-01");
    expect(screen.queryByText("first identity message")).not.toBeInTheDocument();
  });

  it("never writes chat content or identity to browser storage", async () => {
    const user = userEvent.setup();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    mockApi({ "/demo/config": () => json(CONFIG), "/chat": () => json(CHAT_OK) });
    render(<App />);
    await selectUser(user);
    await user.type(screen.getByLabelText("Message"), "secret question");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText(/07700 900002/);
    expect(setItem).not.toHaveBeenCalled();
    expect(document.cookie).toBe("");
  });
});

describe("chat results and tool statuses", () => {
  it("shows the correlation ID and a distinct status for each backend outcome", async () => {
    const user = userEvent.setup();
    mockApi({ "/demo/config": () => json(CONFIG), "/chat": () => json(CHAT_OK) });
    render(<App />);
    await selectUser(user);
    await user.type(screen.getByLabelText("Message"), "q");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByTestId("latest-cid")).toHaveTextContent(CHAT_OK.correlation_id);
    const tones = [...screen.getByTestId("action-list").querySelectorAll("[data-tone]")].map((el) => el.getAttribute("data-tone"));
    expect(tones).toEqual(["allowed", "pending", "denied", "denied", "denied"]);
    expect(screen.getByTestId("action-list").querySelector("[data-tone='pending']")).toHaveTextContent("Pending");
    expect(screen.getByText(/Not found/)).toBeInTheDocument();
  });

  it.each([
    [401, { error: { code: "unauthenticated", message: "Not authenticated.", correlation_id: "c1" } }, "Identity rejected"],
    [503, { error: { code: "service_unavailable", message: "Agent runtime unavailable.", correlation_id: "c2" } }, "Agent runtime unavailable"],
    [500, { error: { code: "internal_error", message: "An internal error occurred.", correlation_id: "c3" } }, "Request failed (500)"],
  ])("renders API error %i safely", async (status, body, title) => {
    const user = userEvent.setup();
    mockApi({ "/demo/config": () => json(CONFIG), "/chat": () => json(body, status, "cid-err") });
    render(<App />);
    await selectUser(user);
    await user.type(screen.getByLabelText("Message"), "q");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(title);
    expect(alert).toHaveTextContent("cid-err");
  });

  it("reports an unreachable backend", async () => {
    const user = userEvent.setup();
    mockApi({
      "/demo/config": () => json(CONFIG),
      "/chat": () => { throw new TypeError("Failed to fetch"); },
    });
    render(<App />);
    await selectUser(user);
    await user.type(screen.getByLabelText("Message"), "q");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Local API unreachable");
  });

  it("explains a disabled demo API when config is 404", async () => {
    mockApi({});
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/DEMO_UI=local/);
  });
});
