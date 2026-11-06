import type { DemoConfig, FixtureUser } from "../api/types";

const ROLE_LABEL: Record<string, string> = {
  support_agent: "Support agent",
  supervisor: "Supervisor",
  tenant_admin: "Tenant admin",
};

interface Props {
  config: DemoConfig | null;
  user: FixtureUser | null;
  onSelectUser: (userId: string) => void;
}

export function Header({ config, user, onSelectUser }: Props) {
  const agent = config?.agent;
  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line bg-white px-4 py-3 md:px-6">
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted">Tenant (fictional)</p>
        <p className="truncate text-sm font-semibold" data-testid="header-tenant">
          {user ? user.tenant_name : "—"}
        </p>
      </div>

      <div className="min-w-0">
        <label htmlFor="identity" className="block text-[11px] font-medium uppercase tracking-wider text-muted">
          Development user
        </label>
        <select
          id="identity"
          className="mt-0.5 max-w-[16rem] rounded-md border border-line bg-white px-2 py-1 text-sm font-medium"
          value={user?.user_id ?? ""}
          onChange={(e) => onSelectUser(e.target.value)}
          disabled={!config}
        >
          {!user && <option value="">Select a fixture user…</option>}
          {config?.users.map((u) => (
            <option key={u.user_id} value={u.user_id}>
              {u.display_name} · {ROLE_LABEL[u.role] ?? u.role} · {u.tenant_name}
            </option>
          ))}
        </select>
      </div>

      <span
        className="inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-900"
        title={config?.identity_notice ?? "Development fixture identities. NOT authentication."}
      >
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-gold-500" />
        Dev fixture identity — not authentication
      </span>

      <div className="ml-auto min-w-0 text-right">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted">Configured model</p>
        <p className="font-mono text-sm" data-testid="header-model">
          {agent?.enabled ? agent.configured_model : "Agent off (fixed reply)"}
        </p>
        {agent?.enabled && <p className="text-[11px] text-muted">fallback: {agent.fallback}</p>}
      </div>
    </header>
  );
}

export { ROLE_LABEL };
