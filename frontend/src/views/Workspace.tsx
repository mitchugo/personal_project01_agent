import { useState } from "react";
import { api } from "../api/client";
import type { ChatResponse, DemoConfig, FixtureUser } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { SafeMarkdown } from "../components/SafeMarkdown";
import { StatusBadge } from "../components/StatusBadge";
import { actionTone, prettyStatus } from "../lib/status";

interface Turn {
  id: number;
  question: string;
  response?: ChatResponse;
  error?: unknown;
}

function suggestions(user: FixtureUser | null): string[] {
  const p = user?.tenant_id === "meridian" ? "mc" : "ns";
  return [
    `What phone number do we have on file for customer ${p}-cust-002?`,
    "What does our refund policy say about approvals?",
    `Save a short draft email to customer ${p}-cust-003 confirming we received their message.`,
  ];
}

interface Props {
  config: DemoConfig | null;
  user: FixtureUser | null;
  onInspect: (correlationId: string) => void;
}

export function Workspace({ config, user, onInspect }: Props) {
  // Chat history lives only in component state: never persisted, and the parent
  // remounts this view (clearing it) whenever the selected identity changes.
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const agentOn = Boolean(config?.agent.enabled);

  async function send(message: string) {
    const text = message.trim();
    if (!user || !text || busy) return;
    const id = Date.now();
    setTurns((t) => [...t, { id, question: text }]);
    setDraft("");
    setBusy(true);
    try {
      const { data } = await api.chat(user.user_id, text);
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, response: data } : turn)));
    } catch (error) {
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, error } : turn)));
    } finally {
      setBusy(false);
    }
  }

  const latest = [...turns].reverse().find((t) => t.response)?.response;

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <section aria-labelledby="chat-title" className="flex min-h-[32rem] flex-col rounded-xl border border-line bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-3.5">
          <div>
            <h2 id="chat-title" className="text-base font-bold">Support workspace</h2>
            <p className="text-xs text-muted">
              Messages go to <span className="font-mono">POST /chat</span> as the selected development user.
            </p>
          </div>
          {agentOn ? (
            <span className="rounded-md border border-line px-2 py-1 text-[11px] font-medium text-muted">
              Each message makes a real, paid model call
            </span>
          ) : (
            <span className="rounded-md border border-line bg-canvas px-2 py-1 text-[11px] font-medium text-muted">
              Agent off — backend returns a fixed reply
            </span>
          )}
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4" aria-live="polite" aria-busy={busy}>
          {!user && <p className="text-sm text-muted">Select a development user in the header to start.</p>}
          {user && turns.length === 0 && (
            <div>
              <p className="text-sm text-muted">Suggested benign prompts (nothing is sent until you choose one):</p>
              <ul className="mt-3 flex flex-col gap-2">
                {suggestions(user).map((s) => (
                  <li key={s}>
                    <button
                      type="button"
                      onClick={() => setDraft(s)}
                      className="w-full rounded-md border border-line px-3 py-2 text-left text-sm hover:border-navy-600 hover:bg-canvas"
                    >
                      {s}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {turns.map((turn) => (
            <article key={turn.id} className="space-y-2">
              <div className="ml-auto w-fit max-w-[85%] rounded-lg bg-navy-900 px-3.5 py-2 text-sm text-white">
                <p className="sr-only">You said:</p>
                <p className="whitespace-pre-wrap break-words">{turn.question}</p>
              </div>
              {!turn.response && !turn.error && (
                <p className="text-sm text-muted" role="status">
                  Waiting for the backend…
                </p>
              )}
              {turn.error !== undefined && <ErrorBanner error={turn.error} />}
              {turn.response && (
                <div className="max-w-[92%] rounded-lg border border-line px-3.5 py-2.5">
                  <p className="sr-only">Assistant reply:</p>
                  <SafeMarkdown text={turn.response.reply} />
                  <p className="mt-2 border-t border-line pt-1.5 font-mono text-[11px] text-muted">
                    correlation_id: {turn.response.correlation_id}
                  </p>
                </div>
              )}
            </article>
          ))}
        </div>

        <form
          className="flex gap-2 border-t border-line p-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send(draft);
          }}
        >
          <label htmlFor="chat-input" className="sr-only">
            Message
          </label>
          <textarea
            id="chat-input"
            rows={2}
            maxLength={4000}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={!user || busy}
            placeholder={user ? "Ask the support agent…" : "Select a development user first"}
            className="min-h-[2.75rem] flex-1 resize-y rounded-md border border-line px-3 py-2 text-sm disabled:bg-canvas"
          />
          <button
            type="submit"
            disabled={!user || busy || !draft.trim()}
            className="self-end rounded-md bg-navy-900 px-4 py-2 text-sm font-semibold text-white hover:bg-navy-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busy ? "Sending…" : "Send"}
          </button>
        </form>
      </section>

      <aside aria-labelledby="activity-title" className="rounded-xl border border-line bg-white">
        <div className="border-b border-line px-5 py-3.5">
          <h2 id="activity-title" className="text-base font-bold">Request activity</h2>
          <p className="text-xs text-muted">What the backend did for the latest request — not the model's claims.</p>
        </div>
        <div className="space-y-4 px-5 py-4 text-sm">
          {!latest && <p className="text-muted">No request yet.</p>}
          {latest && (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
                <dt className="text-muted">Correlation ID</dt>
                <dd className="break-all font-mono" data-testid="latest-cid">{latest.correlation_id}</dd>
                <dt className="text-muted">Acting as</dt>
                <dd className="font-mono">
                  {latest.acting_as.user_id} ({latest.acting_as.role}, {latest.acting_as.tenant_id})
                </dd>
                <dt className="text-muted">Identity source</dt>
                <dd className="font-mono">{latest.acting_as.identity_source}</dd>
                <dt className="text-muted">Agent</dt>
                <dd>{latest.agent_connected ? `connected · ${latest.termination ?? ""}` : "not connected"}</dd>
              </dl>
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">Tool activity</h3>
                {!latest.actions?.length && <p className="mt-1.5 text-muted">No tool calls in this request.</p>}
                <ul className="mt-2 space-y-2" data-testid="action-list">
                  {latest.actions?.map((a, i) => (
                    <li key={i} className="flex items-center justify-between gap-2 rounded-md border border-line px-2.5 py-2">
                      <span className="font-mono text-xs">{a.tool}</span>
                      <StatusBadge tone={actionTone(a.status, a.detail)} label={prettyStatus(a.detail ?? a.status)} />
                    </li>
                  ))}
                </ul>
              </div>
              <button
                type="button"
                onClick={() => onInspect(latest.correlation_id)}
                className="w-full rounded-md border border-navy-700 px-3 py-2 text-sm font-semibold text-navy-900 hover:bg-canvas"
              >
                Open in Security Inspector
              </button>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
