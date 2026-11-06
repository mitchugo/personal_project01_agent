import { ApiError } from "../api/client";

export function describeError(error: unknown): { title: string; detail: string; correlationId: string | null } {
  if (error instanceof ApiError) {
    const titles: Record<number, string> = {
      0: "Local API unreachable",
      401: "Identity rejected",
      403: "Not permitted",
      404: "Not available",
      422: "Request rejected by validation",
      503: "Agent runtime unavailable",
    };
    return {
      title: titles[error.status] ?? `Request failed (${error.status})`,
      detail:
        error.status === 404 && error.message === "Not Found"
          ? "The local demo API is disabled or this item does not exist. Check DEMO_UI=local on the backend."
          : error.message,
      correlationId: error.correlationId,
    };
  }
  return { title: "Unexpected error", detail: "Something went wrong in the UI.", correlationId: null };
}

export function ErrorBanner({ error }: { error: unknown }) {
  const { title, detail, correlationId } = describeError(error);
  return (
    <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
      <p className="font-semibold">{title}</p>
      <p className="mt-0.5">{detail}</p>
      {correlationId && (
        <p className="mt-1 font-mono text-xs text-rose-800">correlation_id: {correlationId}</p>
      )}
    </div>
  );
}
