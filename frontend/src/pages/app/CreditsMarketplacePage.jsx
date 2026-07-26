import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { Card } from "../../components/Card.jsx";
import { Button } from "../../components/Button.jsx";
import { TextInput } from "../../components/TextInput.jsx";

export function CreditsMarketplacePage() {
  const [balance, setBalance] = useState(null);
  const [history, setHistory] = useState([]);
  const [amount, setAmount] = useState("");
  const [priceCents, setPriceCents] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setError(null);
    try {
      const [bRes, hRes] = await Promise.all([api.get("credits/balance"), api.get("credits/history")]);
      const [bData, hData] = await Promise.all([bRes.json(), hRes.json()]);
      if (!bRes.ok) throw new Error(bData?.error?.message || "Could not load balance.");
      setBalance(bData);
      setHistory(hRes.ok ? hData : []);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => { load(); }, []);

  const listForSale = async (e) => {
    e.preventDefault();
    const amt = Number(amount);
    const price = Number(priceCents);
    if (!amt || !price) return setError("Enter a valid amount and price.");
    setBusy(true);
    setError(null);
    try {
      const res = await api.post("credits/marketplace", { amount: amt, price_cents: price });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not list credits.");
      setAmount("");
      setPriceCents("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (!balance) return <p className="text-sm text-gray-400">Loading credits…</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold text-gray-900">Credits & marketplace</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Balance</p>
        <p className="mt-1 text-3xl font-bold text-gray-900">{balance.balance}</p>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">List credits for sale</h2>
        <form onSubmit={listForSale} className="flex flex-wrap gap-2">
          <TextInput type="number" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} className="w-32" />
          <TextInput type="number" placeholder="Price (cents)" value={priceCents} onChange={(e) => setPriceCents(e.target.value)} className="w-40" />
          <Button disabled={busy}>List</Button>
        </form>
        <p className="mt-2 text-xs text-gray-400">
          Browsing/buying other accounts' listings needs a marketplace GET + purchase endpoint on
          credits-service that doesn't exist yet (see this batch's message).
        </p>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">Transaction history</h2>
        {history.length === 0 ? (
          <p className="text-sm text-gray-400">No transactions yet.</p>
        ) : (
          <div className="space-y-1 text-sm">
            {history.map((h) => (
              <div key={h.id} className="flex justify-between border-b border-gray-100 py-1.5 last:border-0">
                <span className="capitalize">{h.transaction_type}</span>
                <span className={h.amount < 0 ? "text-red-600" : "text-green-600"}>{h.amount > 0 ? "+" : ""}{h.amount}</span>
                <span className="text-gray-400">{new Date(h.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}