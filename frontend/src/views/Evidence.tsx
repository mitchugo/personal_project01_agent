import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AttackSpec, EvidenceFile, EvidenceIndex } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { SafeMarkdown } from "../components/SafeMarkdown";

function SpecStatus({ spec }: { spec: AttackSpec }) {
  return spec.status === "executed" ? (
    <span className="rounded-md border border-navy-700 bg-navy-800 px-1.5 py-0.5 text-[11px] font-semibold text-white">
      Evidence recorded
    </span>
  ) : (
    <span className="rounded-md border border-line bg-canvas px-1.5 py-0.5 text-[11px] font-semibold text-muted">
      Prepared — not executed
    </span>
  );
}

function Reserved({ title }: { title: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-3 py-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</p>
      <p className="mt-1 text-sm text-muted">No evidence yet. Populated only from a real campaign run.</p>
    </div>
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
  // Opening this page only reads local files through the API. It never runs attacks or calls a model.
  const [index, setIndex] = useState<EvidenceIndex | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [file, setFile] = useState<EvidenceFile | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.evidence().then((r) => {
      setIndex(r.data);
      setSelected(r.data.specs[0]?.id ?? null);
    }).catch(setError);
  }, []);

  const spec = index?.specs.find((s) => s.id === selected) ?? null;

  async function openFile(id: string) {
    setError(null);
    try {
      setFile((await api.evidenceFile(id)).data);
    } catch (e) {
      setError(e);
    }
  }

  return (
    <section aria-labelledby="evidence-title" className="space-y-5">
      <div>
        <h2 id="evidence-title" className="text-xl font-bold">Attack evidence</h2>
        <p className="max-w-3xl text-sm text-muted">
          Adversarial specifications A01–A08 and previously captured, sanitised evidence. Nothing on this page runs a
          campaign or calls a model.
        </p>
      </div>
      {error !== null && <ErrorBanner error={error} />}

      <div className="grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <nav aria-label="Attack specifications" className="rounded-xl border border-line bg-white">
          <ul className="divide-y divide-line">
            {index?.specs.map((s) => (
              <li key={s.id}>
                <button type="button" onClick={() => setSelected(s.id)} aria-current={s.id === selected ? "true" : undefined}
                  className={`w-full px-4 py-3 text-left ${s.id === selected ? "bg-canvas" : "hover:bg-canvas"}`}>
                  <p className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs font-semibold">{s.id}</span>
                    <SpecStatus spec={s} />
                  </p>
                  <p className="mt-1 text-sm font-medium leading-5">{s.title}</p>
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {spec && (
          <article className="space-y-4 rounded-xl border border-line bg-white p-5" aria-labelledby="spec-title">
            <header className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-mono text-xs text-muted">{spec.id}</p>
                <h3 id="spec-title" className="text-lg font-bold">{spec.title}</h3>
              </div>
              <SpecStatus spec={spec} />
            </header>
            <dl className="grid gap-x-6 gap-y-3 text-sm md:grid-cols-2">
              {([["Objective", spec.objective], ["Asset targeted", spec.asset],
                 ["Attacker-controlled entry point", spec.entry_point]] as const).map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</dt>
                  <dd className="mt-0.5"><SafeMarkdown text={value ?? "—"} /></dd>
                </div>
              ))}
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wider text-muted">Threat references</dt>
                <dd className="mt-1.5 flex flex-wrap gap-1.5">
                  {spec.threat_ids.map((t) => (
                    <span key={t} className="rounded border border-line px-1.5 py-0.5 font-mono text-xs">{t}</span>
                  ))}
                </dd>
              </div>
            </dl>
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted">Expected secure behaviour</h4>
              <SafeMarkdown text={spec.expected ?? "—"} />
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <Reserved title="Before / after comparison" />
              <Reserved title="Exploit observations" />
              <Reserved title="Remediation evidence" />
            </div>
            <details className="rounded-lg border border-line">
              <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">Full specification</summary>
              <div className="border-t border-line px-4 py-2"><SafeMarkdown text={spec.markdown} /></div>
            </details>
          </article>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <nav aria-label="Captured evidence" className="rounded-xl border border-line bg-white p-3">
          <h3 className="px-1 text-sm font-bold">Captured evidence</h3>
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
