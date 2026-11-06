import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { DemoConfig } from "./api/types";
import { ErrorBanner } from "./components/ErrorBanner";
import { Header } from "./components/Header";
import { Sidebar, type View } from "./components/Sidebar";
import { Approvals } from "./views/Approvals";
import { Evidence } from "./views/Evidence";
import { Inspector } from "./views/Inspector";
import { Workspace } from "./views/Workspace";

export default function App() {
  const [view, setView] = useState<View>("workspace");
  const [config, setConfig] = useState<DemoConfig | null>(null);
  const [configError, setConfigError] = useState<unknown>(null);
  // Selected fixture identity is in memory only (never browser storage).
  const [userId, setUserId] = useState<string | null>(null);
  const [focusCid, setFocusCid] = useState<string | null>(null);

  useEffect(() => {
    api.config().then((r) => setConfig(r.data)).catch(setConfigError);
  }, []);

  const user = config?.users.find((u) => u.user_id === userId) ?? null;

  return (
    <div className="flex min-h-full flex-col md:h-full md:flex-row">
      <Sidebar view={view} onSelect={(v) => { setView(v); if (v !== "inspector") setFocusCid(null); }} />
      <div className="flex min-w-0 flex-1 flex-col md:overflow-hidden">
        <Header config={config} user={user} onSelectUser={(id) => { setUserId(id || null); setFocusCid(null); }} />
        <main className="flex-1 overflow-y-auto px-4 py-5 md:px-6">
          <div className="mx-auto max-w-6xl">
            {configError !== null && <div className="mb-4"><ErrorBanner error={configError} /></div>}
            {view === "workspace" && (
              <Workspace key={userId ?? "none"} config={config} user={user}
                onInspect={(cid) => { setFocusCid(cid); setView("inspector"); }} />
            )}
            {view === "inspector" && (
              <Inspector user={user} focusCorrelationId={focusCid} onClearFocus={() => setFocusCid(null)} />
            )}
            {view === "approvals" && <Approvals user={user} />}
            {view === "evidence" && <Evidence />}
          </div>
        </main>
      </div>
    </div>
  );
}
