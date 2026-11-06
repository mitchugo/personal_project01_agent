import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { FixtureUser, InspectorEvent, InspectorResponse } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { actionTone, prettyStatus, refundTone, type Tone } from "../lib/status";

interface Row {
  stage: string;
  title: string;
  tone: Tone;
  label?: string;
  details: [string, string][];
}

const meta = (e: InspectorEvent, key: string) => (e.metadata[key] !== undefined ? String(e.metadata[key]) : undefined);

/** Translate one sanitised audit event into a display row. Only observed fields are shown. */
export function describeEvent(e: InspectorEvent): Row {
  const pick = (...keys: string[]) =>
    keys.flatMap((k) => (meta(e, k) !== undefined ? [[k, meta(e, k)!] as [string, string]] : []));
  switch (e.event_type) {
    case "agent.tool_proposal":
      return {
        stage: "Model proposed",
        title: meta(e, "proposed_tool") ?? "?",
        tone: "proposed",
        details: [["backend outcome", meta(e, "tool_status") ?? "?"], ...pick("iteration")],
      };
    case "tool.invoke": {
      const allowed = meta(e, "decision") === "allow";
      return {
        stage: "Backend decision",
        title: meta(e, "tool") ?? "?",
        tone: allowed ? "allowed" : "denied",
        label: meta(e, "reason"),
        details: pick("resource_id", "result_count", "to_status", "amount_pence", "currency"),
      };
    }
    case "agent.model_call":
      return {
        stage: "Model call",
        title: meta(e, "model") ?? `${meta(e, "configured_model") ?? "model"} (no response)`,
        tone: e.outcome === "success" ? "neutral" : "denied",
        label: meta(e, "stop_reason") ?? meta(e, "reason"),
        details: pick("configured_model", "iteration", "input_tokens", "output_tokens", "cost_usd", "latency_ms",
          "refusal_category"),
      };
    case "agent.run":
      return {
        stage: "Run outcome",
        title: meta(e, "termination") ?? "?",
        tone: meta(e, "termination") === "completed" ? "neutral" : "denied",
        details: pick("model_calls", "tool_calls", "input_tokens", "output_tokens", "cost_usd"),
      };
    case "refund.approval":
    case "refund.execution": {
      const ok = e.outcome === "success";
      const to = meta(e, "to_status");
      return {
        stage: e.event_type === "refund.approval" ? "Human approval" : "Execution",
        title: meta(e, "resource_id") ?? "refund",
        tone: ok ? (to ? refundTone(to) : "allowed") : "denied",
        label: meta(e, "reason"),
        details: pick("from_status", "to_status", "amount_pence", "currency"),
      };
    }
    case "identity.resolve":
      return {
        stage: "Identity",
        title: e.actor_user_id ?? "unresolved",
        tone: e.outcome === "success" ? "neutral" : "denied",
        label: meta(e, "reason") ?? meta(e, "identity_source"),
        details: [],
      };
    case "chat.message":
      return {
        stage: "Chat",
        title: meta(e, "agent_connected") === "true" ? "agent connected" : "agent not connected (fixed reply)",
        tone: "neutral",
        details: [],
      };
    case "http.request":
      return {
        stage: "HTTP",
        title: `${meta(e, "method") ?? ""} ${meta(e, "path") ?? ""}`.trim(),
        tone: e.outcome === "success" ? "neutral" : "denied",
        label: meta(e, "status_code"),
        details: pick("duration_ms"),
      };
    default:
      return { stage: e.event_type, title: e.outcome ?? "", tone: "neutral", details: [] };
  }
}

const STAGE_STYLE: Record<string, string> = {
  "Model proposed": "text-slate-600",
  "Backend decision": "text-navy-800",
};

interface Props {
  user: FixtureUser | null;
  focusCorrelationId: string | null;
  onClearFocus: () => void;
}

export function Inspector({ user, focusCorrelationId, onClearFocus }: Props) {
  const [data, setData] = useState<InspectorResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.inspector(user.user_id, focusCorrelationId ?? undefined);
      setData(data);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [user, focusCorrelationId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="inspector-title" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="inspector-title" className="text-xl font-bold">Security Inspector</h2>
          <p className="max-w-3xl text-sm text-muted">
            Observed audit events for <strong>{user?.tenant_name ?? "—"}</strong>, grouped by correlation ID.
            Model proposals, backend decisions and outcomes are separate events. Data comes from a sanitised,
            in-memory allowlist on the server: no prompts, arguments, customer details or credentials.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {focusCorrelationId && (
            <button type="button" onClick={onClearFocus}
              className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-white">
              Show all requests
            </button>
          )}
          <button type="button" onClick={() => void load()} disabled={!user || loading}
            className="rounded-md bg-navy-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-navy-800 disabled:bg-slate-300">
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {!user && <p className="text-sm text-muted">Select a development user to view their tenant's events.</p>}
      {error !== null && <ErrorBanner error={error} />}
      {data && data.groups.length === 0 && (
        <p className="rounded-lg border border-dashed border-line bg-white px-4 py-6 text-center text-sm text-muted">
          No events recorded for this tenant in the current server process yet. Send a chat message or approve a refund,
          then refresh.
        </p>
      )}

      <div className="space-y-4">
        {data?.groups.map((group) => (
          <article key={group.correlation_id} className="rounded-xl border border-line bg-white">
            <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
              <p className="font-mono text-xs">
                <span className="text-muted">correlation_id </span>
                <span className="font-semibold">{group.correlation_id}</span>
              </p>
              <p className="text-xs text-muted">{group.events[0]?.timestamp?.replace("T", " ").slice(0, 19)} UTC</p>
            </header>
            <ol className="divide-y divide-line">
              {group.events.map((event, i) => {
                const row = describeEvent(event);
                return (
                  <li key={i} className="grid gap-x-4 gap-y-1 px-4 py-2 text-sm sm:grid-cols-[9rem_minmax(0,1fr)_auto]">
                    <span className={`text-xs font-semibold uppercase tracking-wide ${STAGE_STYLE[row.stage] ?? "text-muted"}`}>
                      {row.stage}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs">{row.title}</p>
                      {row.details.length > 0 && (
                        <p className="mt-0.5 flex flex-wrap gap-x-3 text-[11px] text-muted">
                          {row.details.map(([k, v]) => (
                            <span key={k}>
                              {k}: <span className="font-mono">{v}</span>
                            </span>
                          ))}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 sm:justify-end">
                      <StatusBadge tone={row.tone} label={row.label ? prettyStatus(row.label) : undefined} />
                      <time className="font-mono text-[11px] text-muted">{event.timestamp?.slice(11, 19)}</time>
                    </div>
                  </li>
                );
              })}
            </ol>
          </article>
        ))}
      </div>
      {data && <p className="text-[11px] text-muted">Source: {data.source}.</p>}
    </section>
  );
}

export { actionTone };
