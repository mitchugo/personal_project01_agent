import { type ReactNode, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  AssessmentOverview, AssessmentStatus, AssessmentSummary, AttackSpec, EvidenceFile, EvidenceIndex, Finding, RunTrials,
  SpecAssessment, TrialRecord,
} from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { SafeMarkdown } from "../components/SafeMarkdown";

// Opening this page only READS local, sanitised files through the API. It never runs attacks or calls a model.
// Evidence values are untrusted data and are rendered as plain text (no HTML, no Markdown).

export const STATUS_LABEL: Record<AssessmentStatus, string> = {
  prepared: "Prepared — not executed",
  tested_mock: "Tested with mock provider",
  tested_live: "Tested live",
  partially_tested: "Partially tested",
  inconclusive: "Inconclusive",
};

const STATUS_STYLE: Record<AssessmentStatus, string> = {
  prepared: "border-line bg-canvas text-muted",
  tested_mock: "border-slate-300 border-dashed bg-white text-slate-700",
  tested_live: "border-navy-700 bg-navy-800 text-white",
  partially_tested: "border-amber-300 bg-amber-50 text-amber-900",
  inconclusive: "border-rose-200 bg-rose-50 text-rose-800",
};

export const OUTCOME_LABEL: Record<string, string> = {
  NOT_DELIVERED: "Attack not delivered",
  DELIVERED_NOT_ACHIEVED: "Delivered, objective not achieved",
  FOLLOWED_BACKEND_DENIED: "Model followed, backend denied",
  IMPACT_WITHIN_PERMISSIONS: "Unintended impact within permissions",
  BACKEND_BYPASS: "Backend control bypassed",
  INCONCLUSIVE: "Inconclusive (missing evidence)",
  TASK_COMPLETED: "Legitimate task completed",
  TASK_NOT_COMPLETED: "Legitimate task not completed",
};

const RUN_LABEL: Record<string, string> = {
  "s9-mock-obedient": "S9 mock · obedient",
  "s9-mock-resistant": "S9 mock · resistant",
  "s10-live-a01": "S10 live · A01",
  "s10-live-a04": "S10 live · A04",
  "s10-live-a06": "S10 live · A06",
  "s10-live-a08": "S10 live · A08",
  "s10-live-benign": "S10 live · benign",
  "s11-live-a02": "S11 live · A02",
  "s11-live-a03": "S11 live · A03",
  "s11-live-a05": "S11 live · A05",
  "s11-live-a07": "S11 live · A07",
  "s11-live-benign": "S11 live · benign",
};

export const CLASSIFICATION_LABEL: Record<string, string> = {
  confirmed_live: "Confirmed live (synthetic lab)",
  confirmed_mock_only: "Provisional: scripted model only, not reproduced live",
  observation: "Observation",
  mitigated: "Mitigated",
};

// Anything other than an explicit server value is shown as unknown: the page never implies remediation happened.
const REMEDIATION_LABEL: Record<string, string> = { not_started: "Not started", in_progress: "In progress", retested: "Retested" };

const pct = (x: number) => `${Math.round(x * 100)}%`;
const usd = (x: number | null | undefined) => (x == null ? "—" : `$${x.toFixed(4)}`);

function StatusPill({ status }: { status: AssessmentStatus }) {
  return (
    <span data-status={status}
      className={`inline-block whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}

function Label({ children }: { children: ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-wider text-muted">{children}</p>;
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2">
      <Label>{label}</Label>
      <p className="mt-0.5 font-mono text-lg font-semibold">{value}</p>
      {hint && <p className="text-[11px] text-muted">{hint}</p>}
    </div>
  );
}

function AssessmentOverviewPanel({ summary, findings, onFile }: {
  summary: AssessmentSummary; findings: Finding[]; onFile: (id: string) => void;
}) {
  const c = summary.controls_exercised;
  const remediation = summary.remediation_status ? REMEDIATION_LABEL[summary.remediation_status] : "Unknown";
  return (
    <section aria-labelledby="overview-title" data-testid="assessment-overview"
      className="space-y-4 rounded-xl border border-line bg-white p-5">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 id="overview-title" className="text-base font-bold">Assessment overview (pre-remediation)</h3>
          {summary.assessment_period && <p className="text-xs text-muted">{summary.assessment_period}</p>}
        </div>
        <span data-testid="remediation-status"
          className="rounded-md border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[11px] font-semibold text-amber-900">
          Remediation: {remediation}
        </span>
      </header>
      {summary.scope && <p className="max-w-4xl text-sm leading-6">{summary.scope}</p>}

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="rounded-lg border border-line px-3 py-3">
          <Label>Findings by evidence class</Label>
          <ul className="mt-1.5 space-y-1.5 text-xs">
            {findings.map((f) => (
              <li key={f.id} data-testid={`classification-${f.id}`}>
                <span className="font-mono font-semibold">{f.id}</span> · {f.severity ?? "—"}
                <span className="block text-muted">{f.classification ? CLASSIFICATION_LABEL[f.classification] : "Unclassified"}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border border-line px-3 py-3">
          <Label>Backend controls exercised (live)</Label>
          <p className="mt-1 font-mono text-xs font-semibold" data-testid="not-executed">
            {c.not_executed} of {c.proposals} model proposals not executed
          </p>
          <ul className="mt-1 space-y-0.5 font-mono text-xs">
            {c.refusals.map((r) => <li key={`${r.tool}-${r.status}`}>{r.tool} · {r.status} ×{r.count}</li>)}
            <li>HTTP 422 before the model ×{c.requests_rejected_before_model}</li>
          </ul>
          <p className="mt-1.5 text-xs text-muted">
            {c.trials_without_tool_call} attack trials made no tool call, so no backend control was reached in them.
          </p>
        </div>
        <div className="rounded-lg border border-line px-3 py-3">
          <Label>Residual risks</Label>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5">
            {summary.residual_risks.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </div>
      </div>

      {summary.report_links.length > 0 && (
        <div>
          <Label>Reports and sanitised evidence</Label>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {summary.report_links.map((l) => (
              <button key={l.id} type="button" onClick={() => onFile(l.id)}
                className="rounded border border-line px-2 py-0.5 text-xs hover:bg-canvas">{l.label}</button>
            ))}
          </div>
        </div>
      )}
      <p className="text-[11px] text-muted">
        Counts are computed from trial records. Scope, residual risks and remediation status are curated text. No fix has been
        applied or retested; private transcripts are not available here.
      </p>
    </section>
  );
}

function successText(s: SpecAssessment): string {
  if (!s.live.trials) return "Not tested live";
  const ci = s.live.objective_success_ci95;
  return `${s.live.objective_successes}/${s.live.conclusive}` + (ci ? ` (95% CI ${pct(ci[0])}–${pct(ci[1])})` : "");
}

function impactSummary(s: SpecAssessment): string {
  if (!s.live.trials) return s.mock.trials ? "Live: not tested" : "None recorded";
  if (s.live.backend_bypasses) return `${s.live.backend_bypasses} backend bypass(es)`;
  if (s.live.objective_successes) return `${s.live.objective_successes} unintended impact(s)`;
  return "None observed live";
}

function Overview({ specs, titles, selected, onSelect }: {
  specs: SpecAssessment[]; titles: Record<string, string>; selected: string | null; onSelect: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-white">
      <table className="w-full min-w-[56rem] text-left text-sm" aria-label="Attack overview">
        <thead className="border-b border-line text-xs uppercase tracking-wider text-muted">
          <tr>
            {["Attack", "Category", "Status", "Live trials", "Model", "Objective achieved", "Backend denials", "Observed impact", "Evidence"]
              .map((h) => <th key={h} scope="col" className="px-3 py-2 font-semibold">{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {specs.map((s) => (
            <tr key={s.spec_id} className={s.spec_id === selected ? "bg-canvas" : undefined}>
              <td className="px-3 py-2">
                <button type="button" onClick={() => onSelect(s.spec_id)} aria-current={s.spec_id === selected ? "true" : undefined}
                  className="text-left">
                  <span className={`font-mono text-xs font-semibold ${s.spec_id === selected ? "border-b-2 border-gold-500" : ""}`}>{s.spec_id}</span>
                  <span className="block max-w-[14rem] text-xs leading-4 text-muted">{titles[s.spec_id] ?? ""}</span>
                </button>
              </td>
              <td className="px-3 py-2 font-mono text-xs">{s.categories.join(", ") || "—"}</td>
              <td className="px-3 py-2"><StatusPill status={s.status} /></td>
              <td className="px-3 py-2 font-mono text-xs">{s.live.trials || "—"}{s.mock.trials ? <span className="text-muted"> · mock {s.mock.trials}</span> : null}</td>
              <td className="px-3 py-2 font-mono text-xs">{s.live.actual_models.join(", ") || "—"}</td>
              <td className="px-3 py-2 font-mono text-xs" data-testid={`success-${s.spec_id}`}>{s.live.trials ? `${s.live.objective_successes}/${s.live.conclusive}` : "—"}</td>
              <td className="px-3 py-2 font-mono text-xs">{s.live.trials ? s.live.backend_denials : "—"}</td>
              <td className="px-3 py-2 text-xs">{impactSummary(s)}</td>
              <td className="px-3 py-2 font-mono text-[11px] text-muted">{[...s.live.runs, ...s.mock.runs].join(" ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Detail({ spec, result, findings, onRun, onFile }: {
  spec: AttackSpec | null; result: SpecAssessment; findings: Finding[]; onRun: (id: string) => void; onFile: (id: string) => void;
}) {
  const threats = [...new Set([...(spec?.threat_ids ?? []), ...result.dataset_threats])].sort();
  const related = findings.filter((f) => f.affected_specs.includes(result.spec_id));
  const live = result.live;
  return (
    <article className="space-y-4 rounded-xl border border-line bg-white p-5" aria-labelledby="spec-title">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-mono text-xs text-muted">{result.spec_id}</p>
          <h3 id="spec-title" className="text-lg font-bold">{spec?.title ?? result.spec_id}</h3>
        </div>
        <StatusPill status={result.status} />
      </header>

      <dl className="grid gap-x-6 gap-y-3 text-sm md:grid-cols-2">
        <div><dt><Label>Test objective</Label></dt><dd className="mt-0.5">{spec?.objective ?? "—"}</dd></div>
        <div><dt><Label>Attacker-controlled entry point</Label></dt>
          <dd className="mt-0.5">{spec?.entry_point ?? "—"}
            {result.entry_points.length > 0 && <span className="block font-mono text-xs text-muted">dataset: {result.entry_points.join(", ")}</span>}</dd></div>
        <div><dt><Label>Threat references</Label></dt>
          <dd className="mt-1.5 flex flex-wrap gap-1.5">{threats.map((t) => <span key={t} className="rounded border border-line px-1.5 py-0.5 font-mono text-xs">{t}</span>)}</dd></div>
        <div><dt><Label>Trials</Label></dt>
          <dd className="mt-0.5 font-mono text-xs">live {live.trials} ({live.conclusive} conclusive, {live.inconclusive} inconclusive, {live.refused} refused, {live.errored} errored) · mock {result.mock.trials}
            <span className="block text-muted">dataset cases: {result.dataset_cases.join(", ") || "—"}{live.cases.length > 0 && ` · live: ${live.cases.join(", ")}`}</span></dd></div>
        <div><dt><Label>Configured / actual model</Label></dt>
          <dd className="mt-0.5 font-mono text-xs">{live.trials ? `${live.configured_models.join(", ")} / ${live.actual_models.join(", ")} · mismatches ${live.model_mismatches}` : "Not tested live"}</dd></div>
        <div><dt><Label>Attacker objective achieved (live)</Label></dt><dd className="mt-0.5 font-mono text-xs">{successText(result)}</dd></div>
      </dl>

      <div className="grid gap-3 md:grid-cols-3">
        {([["Model behaviour", result.notes.model_behaviour,
            live.trials ? `Compliance indicators: ${live.model_compliance}/${live.conclusive}` : null],
           ["Backend control outcome", result.notes.backend,
            live.trials ? `Denied proposals: ${live.backend_denials} · bypasses: ${live.backend_bypasses}` : null],
           ["Observed application impact", result.notes.impact, live.trials ? impactSummary(result) : null]] as const)
          .map(([title, note, fact]) => (
            <div key={title} className="rounded-lg border border-line px-3 py-3">
              <Label>{title}</Label>
              {fact && <p className="mt-1 font-mono text-xs font-semibold">{fact}</p>}
              <p className="mt-1 text-sm leading-5">{note ?? "No summary recorded."}</p>
            </div>
          ))}
      </div>

      <div>
        <Label>Evidence sources</Label>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {[...live.runs, ...result.mock.runs].map((r) => (
            <button key={r} type="button" onClick={() => onRun(r)} className="rounded border border-line px-2 py-0.5 font-mono text-xs hover:bg-canvas">
              {RUN_LABEL[r] ?? r}
            </button>
          ))}
          {related.map((f) => f.evidence_ref && (
            <button key={f.id} type="button" onClick={() => onFile(f.evidence_ref!)} className="rounded border border-line px-2 py-0.5 font-mono text-xs hover:bg-canvas">
              {f.id}
            </button>
          ))}
          {!live.runs.length && !result.mock.runs.length && <span className="text-sm text-muted">None</span>}
        </div>
      </div>

      <div>
        <Label>Limitations and uncertainty</Label>
        <ul className="mt-1 list-disc pl-5 text-sm leading-6">
          {live.trials > 0 && live.trials < 30 && <li>Small sample: {live.trials} live trials. Rates are descriptive only.</li>}
          {result.status === "tested_mock" && <li>Mock provider only: shows backend behaviour, not real model behaviour.</li>}
          {live.evidence_incomplete > 0 && <li>{live.evidence_incomplete} live trial(s) have incomplete evidence.</li>}
          {result.limitations.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </div>

      <div className="rounded-lg border border-dashed border-line px-3 py-3">
        <Label>Before / after comparison</Label>
        <p className="mt-1 text-sm text-muted">No remediation has been applied or retested yet. Phase C results will appear here.</p>
      </div>

      {spec && (
        <details className="rounded-lg border border-line">
          <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">Full specification</summary>
          <div className="border-t border-line px-4 py-2"><SafeMarkdown text={spec.markdown} /></div>
        </details>
      )}
    </article>
  );
}

function TrialRow({ t }: { t: TrialRecord }) {
  const calls = t.turns.flatMap((x) => x.model_calls);
  return (
    <details className="rounded-lg border border-line" data-testid="trial">
      <summary className="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
        <span className="font-mono text-xs font-semibold">{t.trial_id}</span>
        <span data-outcome={t.outcome} className="rounded border border-line px-1.5 py-0.5 text-[11px]">{OUTCOME_LABEL[t.outcome] ?? t.outcome}</span>
        <span className="text-xs text-muted">{t.status ?? "—"} · {t.mode}</span>
        {!t.evidence_complete && <span className="rounded border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[11px] text-rose-800">Evidence incomplete</span>}
        <span className="ml-auto font-mono text-xs text-muted">{usd(t.usage.cost_usd)} {t.usage.cost_basis === "simulated" ? "(simulated)" : ""}</span>
      </summary>
      <div className="space-y-3 border-t border-line px-3 py-3 text-xs">
        <p className="font-mono">
          {t.timestamp_utc ?? "—"} · {t.principal ?? "—"} ({t.tenant ?? "—"}) · entry {t.entry_point ?? "—"} · configured {t.configured_model ?? "—"} · actual {t.actual_models.join(", ") || "—"}
          {t.model_mismatch ? " · MODEL MISMATCH" : ""} · delivered {String(t.delivered)} · complied {String(t.complied)}
        </p>
        {t.turns.map((turn, i) => (
          <div key={i} className="rounded-md bg-canvas p-2">
            <p className="font-mono">turn {i + 1} · correlation_id {turn.correlation_id ?? "—"} · HTTP {turn.http_status ?? "—"} · {turn.termination ?? "—"}</p>
            <p className="mt-1"><span className="font-semibold">Model proposed:</span> <span className="font-mono">{turn.proposed_tools.join(", ") || "nothing"}</span></p>
            <p><span className="font-semibold">Backend decisions:</span> <span className="font-mono">
              {turn.decisions.filter((d) => d.event !== "identity.resolve").map((d) => `${d.tool ?? d.event}: ${d.decision ?? d.outcome ?? "?"}${d.reason ? ` (${d.reason})` : ""}`).join("; ") || "none"}</span></p>
            <p><span className="font-semibold">Actual tool outcomes:</span> <span className="font-mono">
              {turn.actions.map((a) => `${a.tool}: ${a.status ?? "?"}${a.detail ? ` (${a.detail})` : ""}`).join("; ") || "none"}</span></p>
          </div>
        ))}
        <p className="font-mono">
          DB changes: {Object.entries(t.db_changes).map(([tab, c]) => `${tab} +${c.added}/~${c.changed}`).join(", ") || "none"} ·
          tokens {t.usage.input_tokens ?? "—"} in / {t.usage.output_tokens ?? "—"} out · {calls.length} model call(s) · {t.duration_ms != null ? `${Math.round(t.duration_ms)} ms` : "—"}
        </p>
      </div>
    </details>
  );
}

function TrialExplorer({ runs, runId, onRun, data, filterSpec }: {
  runs: AssessmentOverview["runs"]; runId: string | null; onRun: (id: string) => void; data: RunTrials | null; filterSpec: string | null;
}) {
  const [onlySpec, setOnlySpec] = useState(false);
  const groups = useMemo(() => {
    const out: Record<string, TrialRecord[]> = {};
    for (const t of data?.trials ?? []) {
      if (onlySpec && filterSpec && t.spec_id !== filterSpec) continue;
      (out[t.test_id] ??= []).push(t);
    }
    return out;
  }, [data, onlySpec, filterSpec]);
  return (
    <section aria-labelledby="explorer-title" className="space-y-3 rounded-xl border border-line bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="explorer-title" className="text-base font-bold">Trial explorer</h3>
        {filterSpec && (
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={onlySpec} onChange={(e) => setOnlySpec(e.target.checked)} /> Only {filterSpec}
          </label>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Assessment runs">
        {runs.map((r) => (
          <button key={r.run_id} type="button" onClick={() => onRun(r.run_id)} aria-pressed={r.run_id === runId}
            className={`rounded-md border px-2 py-1 text-xs ${r.run_id === runId ? "border-navy-700 bg-navy-800 text-white" : "border-line hover:bg-canvas"}`}>
            {RUN_LABEL[r.run_id] ?? r.run_id} <span className="opacity-70">({r.trials})</span>
          </button>
        ))}
      </div>
      {data ? (
        <>
          <p className="text-xs text-muted">
            {data.mode === "mock" ? "Mock provider (scripted model): backend behaviour only, not real model behaviour." : "Live model run."}
            {" "}Commit {data.git_commit ?? "—"}{data.git_dirty ? " (uncommitted changes at run time)" : ""} · dataset {data.dataset_version ?? "—"}
            {data.invalid_records > 0 && ` · ${data.invalid_records} malformed record(s) skipped`}
          </p>
          {Object.entries(groups).map(([testId, trials]) => (
            <div key={testId}>
              <p className="mb-1 font-mono text-xs font-semibold">{testId}</p>
              <div className="space-y-1.5">{trials.map((t) => <TrialRow key={t.trial_id} t={t} />)}</div>
            </div>
          ))}
          {Object.keys(groups).length === 0 && <p className="text-sm text-muted">No trials in this selection.</p>}
        </>
      ) : (
        <p className="text-sm text-muted">Select a run to inspect its sanitised trials.</p>
      )}
    </section>
  );
}

function Findings({ findings, onFile }: { findings: Finding[]; onFile: (id: string) => void }) {
  return (
    <section aria-labelledby="findings-title" className="space-y-3">
      <h3 id="findings-title" className="text-base font-bold">Findings and observations</h3>
      <div className="grid gap-3 lg:grid-cols-3">
        {findings.map((f) => (
          <article key={f.id} className="space-y-2 rounded-xl border border-line bg-white p-4" data-testid="finding">
            <header className="flex items-start justify-between gap-2">
              <p className="font-mono text-xs font-semibold">{f.id}</p>
              <span className={`rounded-md border px-1.5 py-0.5 text-[11px] font-semibold ${f.type === "observation" ? "border-line bg-canvas text-muted" : "border-navy-700 text-navy-800"}`}>
                {f.severity ?? "—"}
              </span>
            </header>
            <p className="text-sm font-semibold leading-5">{f.title ?? "—"}</p>
            <dl className="space-y-1 text-xs">
              <div><dt className="inline font-semibold">Status: </dt><dd className="inline">{f.status ?? "—"}</dd></div>
              <div><dt className="inline font-semibold">Mock reproduction: </dt><dd className="inline">{f.reproduction_mock ?? "—"}</dd></div>
              <div><dt className="inline font-semibold">Live reproduction: </dt><dd className="inline">{f.reproduction_live ?? "—"}</dd></div>
              <div><dt className="inline font-semibold">Exploited live: </dt><dd className="inline" data-testid={`exploited-${f.id}`}>{f.exploited_live ? "Yes" : "No"}</dd></div>
              <div><dt className="inline font-semibold">Affects: </dt><dd className="inline font-mono">{f.affected_specs.join(", ") || "—"} · {f.threats.join(", ")}</dd></div>
              <div><dt className="inline font-semibold">Suggested remediation: </dt><dd className="inline">{f.remediation ?? "—"}</dd></div>
              <div><dt className="inline font-semibold">Retest: </dt><dd className="inline">{f.retest_status ?? "—"}</dd></div>
            </dl>
            {f.evidence_ref && (
              <button type="button" onClick={() => onFile(f.evidence_ref!)} className="text-xs font-semibold underline">Open evidence</button>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function renderFile(file: EvidenceFile) {
  if (file.name.endsWith(".md")) return <SafeMarkdown text={file.content} />;
  let text = file.content;
  if (file.name.endsWith(".json")) {
    try {
      text = JSON.stringify(JSON.parse(file.content), null, 2);
    } catch {
      /* show as-is */
    }
  }
  return <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words rounded-md bg-canvas p-3 font-mono text-xs">{text}</pre>;
}

export function Evidence() {
  const [index, setIndex] = useState<EvidenceIndex | null>(null);
  const [assessment, setAssessment] = useState<AssessmentOverview | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [runData, setRunData] = useState<RunTrials | null>(null);
  const [file, setFile] = useState<EvidenceFile | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.evidence().then((r) => {
      setIndex(r.data);
      setSelected((s) => s ?? r.data.specs[0]?.id ?? null);
    }).catch(setError);
    api.assessment().then((r) => setAssessment(r.data)).catch(setError);
  }, []);

  const titles = useMemo(() => Object.fromEntries((index?.specs ?? []).map((s) => [s.id, s.title])), [index]);
  const spec = index?.specs.find((s) => s.id === selected) ?? null;
  const result = assessment?.specs.find((s) => s.spec_id === selected) ?? null;

  async function openRun(id: string) {
    setError(null);
    setRunId(id);
    try {
      setRunData((await api.assessmentTrials(id)).data);
    } catch (e) {
      setError(e);
    }
  }

  async function openFile(id: string) {
    setError(null);
    try {
      setFile((await api.evidenceFile(id)).data);
    } catch (e) {
      setError(e);
    }
  }

  const t = assessment?.totals;
  return (
    <section aria-labelledby="evidence-title" className="space-y-5">
      <div>
        <h2 id="evidence-title" className="text-xl font-bold">Attack evidence</h2>
        <p className="max-w-3xl text-sm text-muted">
          Red-team results for A01–A08 from the local harness, computed from sanitised trial records of every listed run.
          Nothing on this page runs a campaign or calls a model.
        </p>
        {assessment && <p className="mt-1 max-w-3xl text-xs text-muted">{assessment.scope}</p>}
      </div>
      {error !== null && <ErrorBanner error={error} />}

      {assessment?.summary && (
        <AssessmentOverviewPanel summary={assessment.summary} findings={assessment.findings} onFile={(id) => void openFile(id)} />
      )}

      {t && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6" aria-label="Live assessment totals">
          <Stat label="Live attack trials" value={String(t.live_attack_trials)} />
          <Stat label="Objectives achieved" value={`${t.live_objective_successes}/${t.live_attack_trials}`} />
          <Stat label="Backend bypasses" value={String(t.live_backend_bypasses)} />
          <Stat label="Benign tasks" value={`${t.live_benign_completed}/${t.live_benign_trials}`} hint="completed live" />
          <Stat label="Model calls" value={String(t.live_model_calls)} hint={t.live_models.join(", ")} />
          <Stat label="Est. live cost" value={usd(t.live_cost_usd)} hint="app-side estimate" />
        </div>
      )}

      {assessment && <Overview specs={assessment.specs} titles={titles} selected={selected} onSelect={setSelected} />}

      {result && (
        <Detail spec={spec} result={result} findings={assessment?.findings ?? []}
          onRun={(id) => void openRun(id)} onFile={(id) => void openFile(id)} />
      )}

      {assessment && (
        <TrialExplorer runs={assessment.runs} runId={runId} onRun={(id) => void openRun(id)} data={runData} filterSpec={selected} />
      )}

      {assessment && <Findings findings={assessment.findings} onFile={(id) => void openFile(id)} />}

      <section aria-labelledby="phasec-title" className="rounded-xl border border-dashed border-line bg-white p-5">
        <h3 id="phasec-title" className="text-base font-bold">Before / after readiness (Phase C)</h3>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          {assessment && assessment.comparisons.length > 0
            ? `${assessment.comparisons.length} comparison(s) recorded.`
            : "No remediation results exist yet. After fixes are implemented, the same dataset will be re-run (mock and live) and each before/after pair will appear here, linked to its runs. Nothing is shown until real retest evidence exists."}
        </p>
      </section>

      <div className="grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <nav aria-label="Captured evidence" className="rounded-xl border border-line bg-white p-3">
          <h3 className="px-1 text-sm font-bold">Captured evidence files</h3>
          {index?.evidence.map((group) => (
            <div key={group.group} className="mt-3">
              <p className="px-1 font-mono text-[11px] text-muted">{group.group}</p>
              <ul className="mt-1">
                {group.files.map((f) => (
                  <li key={f.id}>
                    <button type="button" onClick={() => void openFile(f.id)}
                      className={`w-full truncate rounded px-2 py-1 text-left text-sm ${file?.id === f.id ? "bg-canvas font-semibold" : "hover:bg-canvas"}`}>
                      {f.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="min-w-0 rounded-xl border border-line bg-white p-5">
          {file ? (
            <>
              <p className="mb-3 font-mono text-xs text-muted">{file.id}</p>
              {renderFile(file)}
            </>
          ) : (
            <p className="text-sm text-muted">Select a file to view sanitised evidence.</p>
          )}
        </div>
      </div>
    </section>
  );
}
