import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ProtectedRoute } from "./ProtectedRoute.jsx";
import * as AuthContext from "./AuthContext.jsx";

function renderWithAuth(authValue) {
  vi.spyOn(AuthContext, "useAuth").mockReturnValue(authValue);
  return render(
    <MemoryRouter initialEntries={["/app"]}>
      <Routes>
        <Route path="/login" element={<div>Login Page</div>} />
        <Route path="/app" element={<ProtectedRoute>{"Protected Content"}</ProtectedRoute>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ProtectedRoute", () => {
  it("redirects unauthenticated users to /login", () => {
    renderWithAuth({ isAuthenticated: false, initializing: false, role: null, platformRole: null });
    expect(screen.getByText("Login Page")).toBeInTheDocument();
  });

  it("shows a loading state while auth is initializing", () => {
    renderWithAuth({ isAuthenticated: false, initializing: true, role: null, platformRole: null });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("renders children for an authenticated user with no role restriction", () => {
    renderWithAuth({ isAuthenticated: true, initializing: false, role: "owner", platformRole: null });
    expect(screen.getByText("Protected Content")).toBeInTheDocument();
  });
});