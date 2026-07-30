import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { Card } from "../components/Card.jsx";
import { Button } from "../components/Button.jsx";
import { TextInput } from "../components/TextInput.jsx";
import { Logo } from "../components/Logo.jsx";

export function OnboardingPage() {
  const { switchAccount, logout, accountId: currentAccountId } = useAuth();
  const navigate = useNavigate();

  const [accounts, setAccounts] = useState(null); // null = loading
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [teamName, setTeamName] = useState("");
  const [inviteToken, setInviteToken] = useState("");

  const loadAccounts = useCallback(async () => {
    setError(null);
    try {
      const res = await api.get("accounts/mine");
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not load your accounts.");
      setAccounts(data);
    } catch (err) {
      setError(err.message);
      setAccounts([]);
    }
  }, []);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  const enterAccount = useCallback(
    async (accountId) => {
      setBusy(true);
      setError(null);
      try {
        const res = await api.post(`accounts/${accountId}/switch`, {});
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error?.message || "Could not enter that account.");
        switchAccount(data.access_token);
        navigate("/app/home");
      } catch (err) {
        setError(err.message);
        setBusy(false);
      }
    },
    [switchAccount, navigate]
  );

  // Signup auto-creates an individual account async (user.registered ->
  // user-service). With exactly one account and no real choice to make,
  // skip straight in instead of making the person click a list of one.
  useEffect(() => {
      if (!currentAccountId && accounts && accounts.length === 1 && !error) {
        enterAccount(accounts[0].account_id);
      }
  }, [accounts]);

  const createTeam = async (e) => {
    e.preventDefault();
    if (!teamName.trim()) return setError("Team name is required.");
    setBusy(true);
    setError(null);
    try {
      const res = await api.post("accounts", { name: teamName.trim() });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not create the team.");
      await enterAccount(data.id);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const acceptInvite = async (e) => {
    e.preventDefault();
    if (!inviteToken.trim()) return setError("Enter your invite code.");
    setBusy(true);
    setError(null);
    try {
      const res = await api.post(`invites/${inviteToken.trim()}/accept`, {});
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "That invite is invalid or expired.");
      switchAccount(data.access_token);
      navigate("/app/home");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (accounts === null || (!currentAccountId && accounts.length === 1 && !error)) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-brand-50">
          <p className="text-sm text-brand-700">Loading your accounts…</p>
        </div>
      );
  }

  return (
    <div className="min-h-screen bg-brand-50 px-4 py-10">
      <div className="mx-auto max-w-lg space-y-6">
        <div className="flex justify-center"><Logo /></div>
        {error && <p className="text-center text-sm text-red-600">{error}</p>}

        {accounts.length > 0 && (
          <Card>
            <h2 className="mb-3 text-sm font-semibold text-gray-900">Your accounts</h2>
            <div className="space-y-2">
              {accounts.map((a) => (
                <button
                  key={a.account_id}
                  disabled={busy}
                  onClick={() => enterAccount(a.account_id)}
                  className="flex w-full items-center justify-between rounded-lg border border-gray-200 px-3 py-2 text-left text-sm hover:bg-brand-50"
                >
                  <span>{a.name ?? "Individual account"}</span>
                  <span className="text-xs text-gray-400">{a.role} · {a.type}</span>
                </button>
              ))}
            </div>
          </Card>
        )}

        {accounts.length === 0 && (
          <Card className="text-center">
            <p className="mb-3 text-sm text-gray-500">
              We're still setting up your individual account — this usually takes a few seconds.
            </p>
            <Button variant="outline" onClick={loadAccounts}>Refresh</Button>
          </Card>
        )}

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">Create a team account</h2>
          <form onSubmit={createTeam} className="flex gap-2">
            <TextInput
              placeholder="Team name"
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              className="flex-1"
            />
            <Button disabled={busy}>Create</Button>
          </form>
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">Have an invite code?</h2>
          <form onSubmit={acceptInvite} className="flex gap-2">
            <TextInput
              placeholder="Invite code"
              value={inviteToken}
              onChange={(e) => setInviteToken(e.target.value)}
              className="flex-1"
            />
            <Button disabled={busy} variant="outline">Join</Button>
          </form>
        </Card>

        <p className="text-center text-sm">
          <button onClick={logout} className="text-gray-400 hover:text-gray-600">Log out</button>
        </p>
      </div>
    </div>
  );
}