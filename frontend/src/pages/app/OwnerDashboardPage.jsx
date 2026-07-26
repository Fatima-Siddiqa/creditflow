import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { StatCard } from "../../components/StatCard.jsx";
import { Card } from "../../components/Card.jsx";

export function OwnerDashboardPage() {
  const { accountId } = useAuth();
  const [profile, setProfile] = useState(null);
  const [balance, setBalance] = useState(null);
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [profileRes, balanceRes, usageRes] = await Promise.all([
          api.get(`accounts/${accountId}`),
          api.get("credits/balance"),
          api.get("usage/summary"),
        ]);
        const [profileData, balanceData, usageData] = await Promise.all([
          profileRes.json(), balanceRes.json(), usageRes.json(),
        ]);
        if (!profileRes.ok) throw new Error(profileData?.error?.message || "Could not load account.");
        setProfile(profileData);
        setBalance(balanceRes.ok ? balanceData : null);
        setUsage(usageRes.ok ? usageData : null);
      } catch (err) {
        setError(err.message);
      }
    })();
  }, [accountId]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!profile) return <p className="text-sm text-gray-400">Loading dashboard…</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold text-gray-900">{profile.name ?? "Your account"}</h1>
      <div className="grid gap-4 sm:grid-cols-4">
        <StatCard label="Plan" value={profile.plan_tier} />
        <StatCard label="Team size" value={profile.seat_count} />
        <StatCard label="Credit balance" value={balance?.balance ?? "—"} />
        <StatCard label="Tokens used (period)" value={usage?.total_tokens ?? "—"} hint={usage?.period} />
      </div>
      {usage?.by_model?.length > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">Usage by model</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-gray-400">
              <tr><th className="pb-2">Model</th><th className="pb-2">Tokens</th><th className="pb-2">Cost</th></tr>
            </thead>
            <tbody>
              {usage.by_model.map((m) => (
                <tr key={m.model} className="border-t border-gray-100">
                  <td className="py-1.5">{m.model}</td>
                  <td className="py-1.5">{m.tokens_used}</td>
                  <td className="py-1.5">${(m.cost_cents / 100).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}