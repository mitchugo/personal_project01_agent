// One visual vocabulary for every action across the UI.
//   proposed  - the model suggested it (no effect on its own)
//   allowed   - the backend authorised and ran it
//   denied    - the backend refused, could not find, or rejected it
//   pending   - waiting for a human decision
//   executed  - a human-approved state change was carried out
//   neutral   - informational

export type Tone = "proposed" | "allowed" | "denied" | "pending" | "executed" | "neutral";

export const TONE_LABEL: Record<Tone, string> = {
  proposed: "Proposed",
  allowed: "Allowed",
  denied: "Denied",
  pending: "Pending",
  executed: "Executed",
  neutral: "Info",
};

const DENIED = new Set(["deny", "denied", "not_found", "invalid", "conflict", "skipped", "error", "rejected"]);

/** Tone for a backend tool outcome reported in a /chat response. */
export function actionTone(status: string, detail?: string | null): Tone {
  if (status === "ok" && detail === "pending_approval") return "pending";
  if (status === "ok") return "allowed";
  if (DENIED.has(status)) return "denied";
  return "neutral";
}

/** Tone for a refund's persisted state. */
export function refundTone(status: string): Tone {
  if (status === "pending_approval") return "pending";
  if (status === "approved") return "allowed";
  if (status === "executed") return "executed";
  return "neutral";
}

/** Tone for an approval-service decision. */
export function serviceTone(status: string, reason: string): Tone {
  if (status === "ok") return reason === "executed" || reason === "already_executed" ? "executed" : "allowed";
  return "denied";
}

export const STATUS_TEXT: Record<string, string> = {
  ok: "OK",
  denied: "Denied",
  not_found: "Not found",
  invalid: "Invalid",
  conflict: "Conflict",
  skipped: "Skipped (limit)",
  error: "Error",
  pending_approval: "Pending approval",
  approved: "Approved",
  executed: "Executed",
};

export function prettyStatus(status: string): string {
  return STATUS_TEXT[status] ?? status.replace(/_/g, " ");
}
