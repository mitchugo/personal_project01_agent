export type View = "workspace" | "inspector" | "approvals" | "evidence";

const ITEMS: { id: View; label: string; hint: string }[] = [
  { id: "workspace", label: "Workspace", hint: "Support chat" },
  { id: "inspector", label: "Security Inspector", hint: "Proposals vs decisions" },
  { id: "approvals", label: "Approvals", hint: "Human refund queue" },
  { id: "evidence", label: "Attack Evidence", hint: "A01–A08 specs" },
];

export function Sidebar({ view, onSelect }: { view: View; onSelect: (v: View) => void }) {
  return (
    <aside className="flex w-full shrink-0 flex-col bg-navy-950 text-white md:h-full md:w-60">
      <div className="flex items-center gap-2.5 px-5 py-4 md:py-5">
        <span aria-hidden="true" className="relative grid h-8 w-8 place-items-center rounded-md bg-navy-800 text-sm font-bold">
          C
          <span className="absolute bottom-1.5 right-1.5 h-1 w-1 rounded-full bg-gold-500" />
        </span>
        <div className="leading-tight">
          <p className="text-sm font-semibold">Chigzio</p>
          <p className="text-[11px] text-slate-400">AI Agent Security Lab</p>
        </div>
      </div>
      <nav aria-label="Primary" className="px-3 pb-3 md:flex-1">
        <ul className="flex gap-1 overflow-x-auto md:flex-col md:overflow-visible">
          {ITEMS.map((item) => {
            const active = item.id === view;
            return (
              <li key={item.id} className="shrink-0">
                <button
                  type="button"
                  onClick={() => onSelect(item.id)}
                  aria-current={active ? "page" : undefined}
                  className={`relative w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                    active ? "bg-navy-800 font-semibold text-white" : "text-slate-300 hover:bg-navy-900 hover:text-white"
                  }`}
                >
                  {active && <span aria-hidden="true" className="absolute inset-y-2 left-0 w-0.5 rounded bg-gold-500" />}
                  <span className="block">{item.label}</span>
                  <span className="hidden text-[11px] font-normal text-slate-400 md:block">{item.hint}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      <p className="hidden border-t border-navy-800 px-5 py-4 text-[11px] leading-4 text-slate-400 md:block">
        Local demonstration only. Synthetic data. Development identities are not authentication.
      </p>
    </aside>
  );
}
