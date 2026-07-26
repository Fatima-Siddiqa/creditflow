import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";

/** allowedRoles: optional array, e.g. ["owner", "admin"] or ["superadmin"].
 * Omit it to just require *any* authenticated user. */
export function ProtectedRoute({ children, allowedRoles }) {
  const { isAuthenticated, initializing, role, platformRole } = useAuth();
  const location = useLocation();

  if (initializing) {
    return <div className="flex h-screen items-center justify-center text-brand-700">Loading…</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && allowedRoles.length > 0) {
    const effectiveRole = platformRole === "superadmin" ? "superadmin" : role;
    if (!allowedRoles.includes(effectiveRole)) {
      return <Navigate to="/app" replace />;
    }
  }

  return children;
}