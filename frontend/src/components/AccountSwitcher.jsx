import { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";

export function AccountSwitcher() {
  const { accountId, switchAccount } = useAuth();
  const [accounts, setAccounts] = useState([]);
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const navigate = useNavigate();

  const loadAccounts = useCallback(async () => {
    const res = await api.get("accounts/mine");
    if (res.ok) setAccounts(await res.json());
  }, []);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  const current = accounts.find((a) => a.account_id === accountId);

  const handleSelect = async (id) => {
    if (id === accountId) return setOpen(false);
    setSwitching(true);
    try {
      const res = await api.post(`accounts/${id}/switch`, {});
      const data = await res.json();
      if (res.ok) {
        switchAccount(data.access_token);
        navigate("/app/home");
      }
    } finally {
      setSwitching(false);
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        {current?.name ?? "Select account"}
        <span className="text-xs text-gray-400">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-56 rounded-lg border border-gray-100 bg-white py-1 shadow-lg">
          {accounts.map((a) => (
            <button
              key={a.account_id}
              disabled={switching}
              onClick={() => handleSelect(a.account_id)}
              className={`block w-full px-3 py-2 text-left text-sm hover:bg-brand-50 ${
                a.account_id === accountId ? "font-semibold text-brand-700" : "text-gray-700"
              }`}
            >
              {a.name ?? "Individual account"} <span className="text-xs text-gray-400">· {a.role}</span>
            </button>
          ))}
          <div className="mt-1 border-t border-gray-100 pt-1">
            <Link
              to="/app/onboarding"
              onClick={() => setOpen(false)}
              className="block px-3 py-2 text-left text-sm text-brand-600 hover:bg-brand-50"
            >
              + Create or join another
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}