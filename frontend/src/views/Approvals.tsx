import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { FixtureUser, Refund, RefundsResponse, ServiceResult } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { prettyStatus, refundTone, serviceTone } from "../lib/status";

const money = (pence: number, currency: string) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(pence / 100);

const REASON_TEXT: Record<string, string> = {
  approved: "Approved by the backend.",
  executed: "Executed (simulated ledger entry).",
  already_executed: "Already executed — idempotent, nothing new was written.",
  role_not_permitted: "Your fixture role is not permitted to do this.",
  unverified_principal: "Identity did not re-verify against the users table.",
  not_found_in_tenant: "No such refund in your tenant.",
  already_decided: "This refund is no longer pending (replay or double approval).",
  self_approval: "Separation of duties: you cannot approve your own request.",
  binding_mismatch: "Confirmed values do not match the stored request.",
  not_approved: "Cannot execute: the refund is not approved.",
  concurrent_change: "The refund changed concurrently; nothing was applied.",
  ledger_conflict: "Ledger conflict; the transaction was rolled back.",
};

interface Outcome {
  refundId: string;
  result?: ServiceResult;
  correlationId: string | null;
}

export function Approvals({ user }: { user: FixtureUser | null }) {
  const [data, setData] = useState<RefundsResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [confirming, setConfirming] = useState<Refund | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    setError(null);
    try {
      setData((await api.refunds(user.user_id)).data);
    } catch (e) {
      setData(null);
      setError(e);
    }
  }, [user]);

  useEffect(() => {
    setOutcome(null);
    setConfirming(null);
    void load();
  }, [load]);

  async function run(kind: "approve" | "execute", refund: Refund) {
    if (!user) return;
    setBusy(true);
    try {
      const res =
        kind === "approve"
          ? await api.approve(user.user_id, refund.refund_id, {
              customer_id: refund.customer_id,
              amount_pence: refund.amount_pence,
              currency: refund.currency,
            })
          : await api.execute(user.user_id, refund.refund_id);
      setOutcome({ refundId: refund.refund_id, result: res.data, correlationId: res.correlationId });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
      setConfirming(null);
      void load();
    }
  }

  return (
    <section aria-labelledby="approvals-title" className="space-y-4">
      <div>
        <h2 id="approvals-title" className="text-xl font-bold">Human approval queue</h2>
        <p className="max-w-3xl text-sm text-muted">
          Simulated supervisor workflow for synthetic refunds, outside the agent's tool gateway. Every action calls the
          backend approval service, which re-checks supervisor role, identity, same tenant, separation of duties and the
          exact customer, amount and currency. The UI does not pre-filter by role: the backend decides.
        </p>
      </div>

      <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-900">
        Acting as <strong>{user ? `${user.display_name} (${user.user_id})` : "—"}</strong>. This is a selected
        development fixture, <strong>not authentication</strong>. No money moves; execution writes a simulated ledger row.
      </div>

      {error !== null && <ErrorBanner error={error} />}

      {outcome?.result && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-white px-4 py-3 text-sm">
          <StatusBadge tone={serviceTone(outcome.result.status, outcome.result.reason)}
            label={prettyStatus(outcome.result.reason)} />
          <span>{REASON_TEXT[outcome.result.reason] ?? outcome.result.reason}</span>
          <span className="font-mono text-[11px] text-muted">
            {outcome.result.action} · {outcome.refundId.slice(0, 15)}… · correlation_id {outcome.correlationId}
          </span>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-line bg-white">
        <table className="w-full min-w-[46rem] text-left text-sm">
          <caption className="sr-only">Refund requests for your tenant</caption>
          <thead className="border-b border-line text-[11px] uppercase tracking-wider text-muted">
            <tr>
              <th scope="col" className="px-4 py-2.5 font-semibold">Refund</th>
              <th scope="col" className="px-4 py-2.5 font-semibold">Customer</th>
              <th scope="col" className="px-4 py-2.5 font-semibold">Amount</th>
              <th scope="col" className="px-4 py-2.5 font-semibold">Requested by</th>
              <th scope="col" className="px-4 py-2.5 font-semibold">Status</th>
              <th scope="col" className="px-4 py-2.5 font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data?.refunds.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted">
                  No refund requests in this tenant. Ask the agent to request one in the Workspace.
                </td>
              </tr>
            )}
            {data?.refunds.map((r) => (
              <tr key={r.refund_id} className="align-top">
                <td className="px-4 py-3">
                  <p className="font-mono text-xs">{r.refund_id.slice(0, 15)}…</p>
                  <p className="mt-1 max-w-[16rem] whitespace-pre-wrap break-words text-xs text-muted"
                    title="Untrusted text, shown as plain text">
                    {r.reason}
                  </p>
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">{r.customer_id}</td>
                <td className="whitespace-nowrap px-4 py-3 font-semibold">{money(r.amount_pence, r.currency)}</td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">
                  {r.requested_by}
                  {r.approved_by && <p className="text-muted">approved: {r.approved_by}</p>}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge tone={refundTone(r.status)} label={prettyStatus(r.status)} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    {r.status === "pending_approval" && (
                      <button type="button" disabled={busy} onClick={() => setConfirming(r)}
                        className="rounded-md bg-navy-900 px-2.5 py-1 text-xs font-semibold text-white hover:bg-navy-800 disabled:bg-slate-300">
                        Approve…
                      </button>
                    )}
                    {r.status !== "executed" && (
                      <button type="button" disabled={busy} onClick={() => void run("execute", r)}
                        className="rounded-md border border-navy-700 px-2.5 py-1 text-xs font-semibold text-navy-900 hover:bg-canvas disabled:opacity-50">
                        Execute
                      </button>
                    )}
                    <button type="button" disabled
                      title="Not implemented: the backend has no reject transition."
                      className="cursor-not-allowed rounded-md border border-line px-2.5 py-1 text-xs text-muted">
                      Reject (not implemented)
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {confirming && (
        <div role="dialog" aria-modal="true" aria-labelledby="confirm-title"
          className="fixed inset-0 z-10 grid place-items-center bg-navy-950/40 p-4">
          <div className="w-full max-w-md rounded-xl border border-line bg-white p-5 shadow-lg">
            <h3 id="confirm-title" className="text-base font-bold">Confirm exact approval values</h3>
            <p className="mt-1 text-sm text-muted">
              The backend approves only if every value matches the stored request and you are a different supervisor
              in the same tenant.
            </p>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted">Refund</dt><dd className="break-all font-mono text-xs">{confirming.refund_id}</dd>
              <dt className="text-muted">Customer</dt><dd className="font-mono">{confirming.customer_id}</dd>
              <dt className="text-muted">Amount</dt><dd className="font-semibold">{money(confirming.amount_pence, confirming.currency)}</dd>
              <dt className="text-muted">Currency</dt><dd>{confirming.currency}</dd>
            </dl>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setConfirming(null)}
                className="rounded-md border border-line px-3 py-1.5 text-sm">Cancel</button>
              <button type="button" disabled={busy} onClick={() => void run("approve", confirming)}
                className="rounded-md bg-navy-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-navy-800">
                Send approval to backend
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
