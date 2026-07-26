import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ProtectedRoute } from "./ProtectedRoute.jsx";
import * as AuthContext from "./AuthContext.jsx";

function renderWithRole(role, platformRole, allowedRoles) {
  vi.spyOn(AuthContext, "useAuth").mockReturnValue({
    isAuthenticated: true,
    initializing: false,
    role,
    platformRole,
  });
  return render(
    <MemoryRouter initialEntries={["/admin"]}>
      <Routes>
        <Route path="/app" element={<div>App Home</div>} />
        <Route
          path="/admin"
          element={<ProtectedRoute allowedRoles={allowedRoles}>{"Admin Console"}</ProtectedRoute>}
        />
      </Routes>
    </MemoryRouter>
  );
}

describe("ProtectedRoute role gating", () => {
  it("blocks a wrong-role user and redirects to /app", () => {
    renderWithRole("member", null, ["superadmin"]);
    expect(screen.getByText("App Home")).toBeInTheDocument();
  });

  it("lets a SuperAdmin through regardless of the account-level role claim", () => {
    renderWithRole("member", "superadmin", ["superadmin"]);
    expect(screen.getByText("Admin Console")).toBeInTheDocument();
  });
});