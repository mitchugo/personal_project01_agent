import { vi } from "vitest";
import type { DemoConfig } from "../api/types";

export const CONFIG: DemoConfig = {
  identity_notice: "Development fixture identities. NOT authentication.",
  users: [
    { user_id: "ns-agent-01", display_name: "Jordan Blake", role: "support_agent", tenant_id: "northstar", tenant_name: "Northstar Insurance" },
    { user_id: "ns-super-01", display_name: "Morgan Ellis", role: "supervisor", tenant_id: "northstar", tenant_name: "Northstar Insurance" },
    { user_id: "mc-agent-01", display_name: "Riley Okonjo", role: "support_agent", tenant_id: "meridian", tenant_name: "Meridian Cover" },
  ],
  agent: { enabled: true, provider: "anthropic", configured_model: "claude-sonnet-5-5", fallback: "off" },
};

export function json(body: unknown, status = 200, correlationId = "cid-test-123"): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "X-Correlation-ID": correlationId },
  });
}

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

/** Stubs fetch with per-path handlers; records every call. */
export function mockApi(routes: Record<string, Handler>) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    calls.push({ url, init });
    const key = Object.keys(routes).find((k) => url.startsWith(`/api${k}`));
    if (!key) return json({ error: { code: "not_found", message: "Not Found", correlation_id: "x" } }, 404);
    return routes[key](url, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function headerOf(init: RequestInit, name: string): string | undefined {
  return (init.headers as Record<string, string> | undefined)?.[name];
}
