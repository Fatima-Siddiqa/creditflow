import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { Card } from "../../components/Card.jsx";
import { Button } from "../../components/Button.jsx";

const PLANS = ["pro", "team"];

// Keep in sync with credits-service's PLAN_CREDIT_GRANTS
// ({"free": 0, "pro": 1000, "team": 5000}). Ideally this lives behind a
// shared GET /billing/plans endpoint instead of being hardcoded in three
// places, but that's a bigger refactor — flagging it here for now.
const PLAN_DETAILS = {
  pro: {
    price: "$10/mo",
    credits: 1000,
    features: ["1,000 AI credits/mo", "LinkedIn publishing", "Priority support"],
  },
  team: {
    price: "$40/mo",
    credits: 5000,
    features: ["5,000 AI credits/mo", "Up to 10 team members", "LinkedIn publishing", "Priority support"],
  },
};

export function BillingPage() {
  const { accountId } = useAuth();
  const [profile, setProfile] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setError(null);
    try {
      const [pRes, iRes] = await Promise.all([api.get(`accounts/${accountId}`), api.get("billing/invoices")]);
      const [pData, iData] = await Promise.all([pRes.json(), iRes.json()]);
      if (!pRes.ok) throw new Error(pData?.error?.message || "Could not load account.");
      setProfile(pData);
      setInvoices(iRes.ok ? iData : []);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => { load(); }, [accountId]); // eslint-disable-line react-hooks/exhaustive-deps

  const subscribe = async (planTier) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.post("billing/checkout-session", { plan_tier: planTier });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not start checkout.");
      window.location.href = data.checkout_url; // Stripe sandbox Checkout redirect
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  // Simplified: only two paid tiers, so "not team" == pro is always the
  // downgrade direction and vice versa. Revisit if a 4th tier is added.
  const changePlan = async (planTier, direction) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.post(`billing/${direction}`, { plan_tier: planTier });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not change plan.");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (!profile) return <p className="text-sm text-gray-400">Loading billing…</p>;
  const onFree = profile.plan_tier === "free";

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold text-gray-900">Billing & invoices</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <h2 className="mb-2 text-sm font-semibold text-gray-900">Current plan</h2>
        <p className="mb-4 text-2xl font-bold capitalize text-gray-900">{profile.plan_tier}</p>

        {/* Plan comparison — shows price/credits/features before the user commits to Stripe checkout */}
        <div className="mb-4 grid gap-4 sm:grid-cols-2">
          {PLANS.map((p) => (
            <div
              key={p}
              className={`rounded-lg border p-4 ${profile.plan_tier === p ? "border-gray-900" : "border-gray-200"}`}
            >
              <p className="font-semibold capitalize text-gray-900">{p}</p>
              <p className="text-xl font-bold text-gray-900">{PLAN_DETAILS[p].price}</p>
              <p className="mb-2 text-sm text-gray-500">{PLAN_DETAILS[p].credits.toLocaleString()} credits/mo</p>
              <ul className="list-inside list-disc text-xs text-gray-500">
                {PLAN_DETAILS[p].features.map((f) => <li key={f}>{f}</li>)}
              </ul>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-2">
          {onFree
            ? PLANS.map((p) => <Button key={p} disabled={busy} onClick={() => subscribe(p)}>Upgrade to {p}</Button>)
            : PLANS.filter((p) => p !== profile.plan_tier).map((p) => (
                <Button key={p} variant="outline" disabled={busy} onClick={() => changePlan(p, p === "team" ? "upgrade" : "downgrade")}>
                  Switch to {p}
                </Button>
              ))}
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">Invoice history</h2>
        {invoices.length === 0 ? (
          <p className="text-sm text-gray-400">No invoices yet.</p>
        ) : (
          <div className="space-y-1 text-sm">
            {invoices.map((inv) => (
              <div key={inv.id} className="flex justify-between border-b border-gray-100 py-1.5 last:border-0">
                <span>{new Date(inv.created_at).toLocaleDateString()}</span>
                <span>${(inv.amount_cents / 100).toFixed(2)}</span>
                <span className="capitalize text-gray-400">{inv.status}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}