import { TONE_LABEL, type Tone } from "../lib/status";

const STYLES: Record<Tone, string> = {
  proposed: "border-slate-300 bg-white text-slate-700 border-dashed",
  allowed: "border-emerald-200 bg-emerald-50 text-emerald-800",
  denied: "border-rose-200 bg-rose-50 text-rose-800",
  pending: "border-amber-300 bg-amber-50 text-amber-900",
  executed: "border-navy-700 bg-navy-800 text-white",
  neutral: "border-line bg-canvas text-muted",
};

const ICON: Record<Tone, string> = {
  proposed: "◇",
  allowed: "✓",
  denied: "✕",
  pending: "◷",
  executed: "■",
  neutral: "•",
};

interface Props {
  tone: Tone;
  /** Optional precise status shown after the tone, e.g. "Not found". */
  label?: string;
}

export function StatusBadge({ tone, label }: Props) {
  return (
    <span
      data-tone={tone}
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${STYLES[tone]}`}
    >
      <span aria-hidden="true">{ICON[tone]}</span>
      <span>{TONE_LABEL[tone]}</span>
      {label && !label.toLowerCase().startsWith(TONE_LABEL[tone].toLowerCase()) && (
        <span className="font-medium normal-case tracking-normal">· {label}</span>
      )}
    </span>
  );
}
