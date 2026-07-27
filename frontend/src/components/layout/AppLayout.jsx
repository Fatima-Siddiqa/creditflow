import { Outlet, Navigate, NavLink } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext.jsx";
import { Logo } from "../Logo.jsx";
import { AccountSwitcher } from "../AccountSwitcher.jsx";
import { Button } from "../Button.jsx";
import { useAuth } from "../../auth/AuthContext.jsx";

const navLinkClass = ({ isActive }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "bg-brand-50 text-brand-700" : "text-gray-500 hover:text-gray-800"}`;

export function AppLayout() {
  const { accountId, role, platformRole, logout } = useAuth();

  if (!accountId) return <Navigate to="/app/onboarding" replace />;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex items-center justify-between border-b border-gray-100 bg-white px-6 py-3">
        <div className="flex items-center gap-6">
          <Logo size={32} />
          <nav className="flex items-center gap-1">
            <NavLink to="/app/home" className={navLinkClass} end>Dashboard</NavLink>
            <NavLink to="/app/studio" className={navLinkClass}>Studio</NavLink>
            <NavLink to="/app/calendar" className={navLinkClass}>Calendar</NavLink>
            <NavLink to="/app/linkedin" className={navLinkClass}>LinkedIn</NavLink>
            {role === "owner" && <NavLink to="/app/team" className={navLinkClass}>Team</NavLink>}
            {role === "owner" && <NavLink to="/app/billing" className={navLinkClass}>Billing</NavLink>}
            {role === "owner" && <NavLink to="/app/credits" className={navLinkClass}>Credits</NavLink>}
            {platformRole === "superadmin" && <NavLink to="/app/admin" className={navLinkClass}>Admin</NavLink>}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <AccountSwitcher />
          <Button variant="ghost" onClick={logout}>Log out</Button>
        </div>
      </header>
      <main className="p-6"><Outlet /></main>
    </div>
  );
}