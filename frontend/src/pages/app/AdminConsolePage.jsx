import { useEffect, useState, useCallback } from "react";
import { api } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { Card } from "../../components/Card.jsx";
import { Button } from "../../components/Button.jsx";
import { TextInput } from "../../components/TextInput.jsx";
import { ConfirmModal } from "../../components/ConfirmModal.jsx";

const TABS = ["accounts", "sessions", "audit"];

export function AdminConsolePage() {
  const [tab, setTab] = useState("accounts");
  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold text-gray-900">Platform admin console</h1>
      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium capitalize ${
              tab === t ? "border-b-2 border-brand-600 text-brand-700" : "text-gray-500 hover:text-gray-800"
            }`}
          >
            {t === "audit" ? "Audit log" : t}
          </button>
        ))}
      </div>
      {tab === "accounts" && <AccountsTab />}
      {tab === "sessions" && <SessionsTab />}
      {tab === "audit" && <AuditLogTab />}
    </div>
  );
}

// ---- Cross-account directory + per-account overview ----
function AccountsTab() {
  const [search, setSearch] = useState("");
  const [accounts, setAccounts] = useState([]);
  const [expanded, setExpanded] = useState(null); // account_id
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.get(`admin/accounts?search=${encodeURIComponent(search)}&limit=50&offset=0`);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not load accounts.");
      setAccounts(data);
    } catch (err) {
      setError(err.message);
    }
  }, [search]);

  useEffect(() => { load(); }, [load]);

  const toggleOverview = async (accountId) => {
    if (expanded === accountId) return setExpanded(null);
    setExpanded(accountId);
    setOverview(null);
    try {
      const res = await api.get(`admin/accounts/${accountId}/overview`);
      const data = await res.json();
      if (res.ok) setOverview(data);
    } catch {
      /* overview is a nice-to-have expansion; row still shows without it */
    }
  };

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-red-600">{error}</p>}
      <form onSubmit={(e) => { e.preventDefault(); load(); }} className="flex gap-2">
        <TextInput placeholder="Search accounts…" value={search} onChange={(e) => setSearch(e.target.value)} className="flex-1" />
        <Button type="submit" variant="outline">Search</Button>
      </form>
      <Card>
        <div className="divide-y divide-gray-100">
          {accounts.map((a) => (
            <div key={a.id}>
              <button onClick={() => toggleOverview(a.id)} className="flex w-full items-center justify-between py-2 text-left text-sm hover:bg-gray-50">
                <span className="font-medium text-gray-800">{a.name ?? "Individual account"}</span>
                <span className="text-xs text-gray-400">{a.type} · {a.plan_tier}</span>
              </button>
              {expanded === a.id && (
                <div className="mb-2 grid grid-cols-4 gap-3 rounded-lg bg-gray-50 p-3 text-xs text-gray-600">
                  {overview ? (
                    <>
                      <span>Seats: {overview.seat_count}</span>
                      <span>Credits: {overview.credit_balance}</span>
                      <span>Tokens (period): {overview.usage_tokens_this_period}</span>
                      <span>Cost: ${(overview.usage_cost_cents_this_period / 100).toFixed(2)}</span>
                    </>
                  ) : (
                    <span>Loading overview…</span>
                  )}
                </div>
              )}
            </div>
          ))}
          {accounts.length === 0 && <p className="py-4 text-sm text-gray-400">No accounts found.</p>}
        </div>
      </Card>
    </div>
  );
}

// ---- Active sessions (platform-wide -- see note below) ----
function SessionsTab() {
  const { accountId, platformRole } = useAuth();
  const [sessions, setSessions] = useState([]);
  const [error, setError] = useState(null);
  const [pendingRevoke, setPendingRevoke] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      // account_id is a required query param for the permission check, but
      // the backend's jti store isn't tagged by account -- it returns every
      // live session platform-wide once you're authorized to ask at all.
      const res = await api.get(`admin/sessions?account_id=${accountId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not load sessions.");
      setSessions(data);
    } catch (err) {
      setError(err.message);
    }
  }, [accountId]);

  useEffect(() => { load(); }, [load]);

  const confirmRevoke = async () => {
    if (!pendingRevoke) return;
    setBusy(true);
    try {
      const res = await api.delete(`admin/sessions/${pendingRevoke}`);
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data?.error?.message || "Could not revoke session.");
      }
      setPendingRevoke(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-red-600">{error}</p>}
      <p className="text-xs text-gray-400">
        Shows every currently live session platform-wide (the token store isn't tagged by account yet).
      </p>
      <Card>
        <div className="divide-y divide-gray-100 text-sm">
          {sessions.map((s) => (
            <div key={s.jti} className="flex items-center justify-between py-2">
              <span className="font-mono text-xs text-gray-600">{s.jti}</span>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-400">expires in {s.ttl_seconds}s</span>
                {platformRole === "superadmin" && (
                  <Button variant="danger" onClick={() => setPendingRevoke(s.jti)}>Revoke</Button>
                )}
              </div>
            </div>
          ))}
          {sessions.length === 0 && <p className="py-4 text-sm text-gray-400">No active sessions.</p>}
        </div>
      </Card>
      <ConfirmModal
        open={!!pendingRevoke}
        title="Revoke this session?"
        description="The holder of this token will be signed out immediately."
        confirmLabel="Revoke"
        busy={busy}
        onCancel={() => setPendingRevoke(null)}
        onConfirm={confirmRevoke}
      />
    </div>
  );
}

// ---- Audit log ----
function AuditLogTab() {
  const [accountId, setAccountId] = useState("");
  const [eventType, setEventType] = useState("");
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (accountId) params.set("account_id", accountId);
      if (eventType) params.set("event_type", eventType);
      const res = await api.get(`admin/audit-log?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not load the audit log.");
      setEntries(data);
    } catch (err) {
      setError(err.message);
    }
  }, [accountId, eventType]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-red-600">{error}</p>}
      <form onSubmit={(e) => { e.preventDefault(); load(); }} className="flex flex-wrap gap-2">
        <TextInput placeholder="Filter by account_id" value={accountId} onChange={(e) => setAccountId(e.target.value)} className="flex-1" />
        <TextInput placeholder="Filter by event_type" value={eventType} onChange={(e) => setEventType(e.target.value)} className="flex-1" />
        <Button type="submit" variant="outline">Filter</Button>
      </form>
      <Card>
        <div className="divide-y divide-gray-100 text-sm">
          {entries.map((e) => (
            <div key={e.event_id} className="py-2">
              <div className="flex items-center justify-between">
                <span className="font-medium text-gray-800">{e.event_type}</span>
                <span className="text-xs text-gray-400">{new Date(e.occurred_at).toLocaleString()}</span>
              </div>
              <p className="text-xs text-gray-400">account: {e.account_id ?? "—"}</p>
              <pre className="mt-1 overflow-x-auto rounded bg-gray-50 p-2 text-xs text-gray-500">
                {JSON.stringify(e.payload, null, 2)}
              </pre>
            </div>
          ))}
          {entries.length === 0 && <p className="py-4 text-sm text-gray-400">No matching events.</p>}
        </div>
      </Card>
    </div>
  );
}