import { Outlet, Navigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext.jsx";
import { Logo } from "../Logo.jsx";
import { AccountSwitcher } from "../AccountSwitcher.jsx";
import { Button } from "../Button.jsx";

export function AppLayout() {
  const { accountId, logout } = useAuth();

  // No scoped account yet (e.g. direct nav or a hard refresh mid-onboarding)
  // -- send back rather than rendering a shell with nothing inside it.
  if (!accountId) return <Navigate to="/app/onboarding" replace />;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex items-center justify-between border-b border-gray-100 bg-white px-6 py-3">
        <Logo size={32} />
        <div className="flex items-center gap-3">
          <AccountSwitcher />
          <Button variant="ghost" onClick={logout}>Log out</Button>
        </div>
      </header>
      <main className="p-6"><Outlet /></main>
    </div>
  );
}