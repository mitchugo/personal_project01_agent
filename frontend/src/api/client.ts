// The only module that performs HTTP requests.
//
// * Same-origin "/api" (Vite dev proxy -> FastAPI). The browser never talks to SQLite or Anthropic.
// * Identity = X-Dev-User-Id header only (a LOCAL dev fixture, not authentication).
//   Role and tenant are resolved by the backend from its database.
// * Nothing is written to localStorage/sessionStorage/cookies.

export const API_BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly correlationId: string | null;
  readonly body: unknown;

  constructor(status: number, code: string, message: string, correlationId: string | null, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
    this.body = body;
  }
}

export interface ApiResult<T> {
  data: T;
  status: number;
  correlationId: string | null;
}

interface RequestOptions {
  userId?: string | null;
  body?: unknown;
  /** Return non-2xx JSON bodies as data instead of throwing (used for approval decisions). */
  acceptStatuses?: number[];
}

async function request<T>(method: "GET" | "POST", path: string, opts: RequestOptions = {}): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.userId) headers["X-Dev-User-Id"] = opts.userId;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      credentials: "omit",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network_error", "The local API server could not be reached.", null, null);
  }

  const correlationId = response.headers.get("X-Correlation-ID");
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (response.ok || opts.acceptStatuses?.includes(response.status)) {
    return { data: body as T, status: response.status, correlationId };
  }
  const error = (body as { error?: { code?: string; message?: string } } | null)?.error;
  throw new ApiError(
    response.status,
    error?.code ?? "http_error",
    error?.message ?? `Request failed (${response.status}).`,
    correlationId,
    body,
  );
}

export const api = {
  config: () => request<import("./types").DemoConfig>("GET", "/demo/config"),
  chat: (userId: string, message: string) =>
    request<import("./types").ChatResponse>("POST", "/chat", { userId, body: { message } }),
  inspector: (userId: string, correlationId?: string) =>
    request<import("./types").InspectorResponse>(
      "GET",
      `/demo/inspector${correlationId ? `?correlation_id=${encodeURIComponent(correlationId)}` : ""}`,
      { userId },
    ),
  refunds: (userId: string) => request<import("./types").RefundsResponse>("GET", "/demo/refunds", { userId }),
  approve: (userId: string, refundId: string, binding: { customer_id: string; amount_pence: number; currency: "GBP" }) =>
    request<import("./types").ServiceResult>("POST", `/demo/refunds/${encodeURIComponent(refundId)}/approve`, {
      userId,
      body: binding,
      acceptStatuses: [403, 404, 409],
    }),
  execute: (userId: string, refundId: string) =>
    request<import("./types").ServiceResult>("POST", `/demo/refunds/${encodeURIComponent(refundId)}/execute`, {
      userId,
      acceptStatuses: [403, 404, 409],
    }),
  evidence: () => request<import("./types").EvidenceIndex>("GET", "/demo/evidence"),
  evidenceFile: (id: string) =>
    request<import("./types").EvidenceFile>("GET", `/demo/evidence/file?id=${encodeURIComponent(id)}`),
};
