import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AdminConsolePage } from "./AdminConsolePage.jsx";
import * as AuthContext from "../../auth/AuthContext.jsx";

function jsonResponse(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 400, json: async () => body, clone() { return this; } });
}

describe("AdminConsolePage", () => {
  it("shows the cross-account directory by default", async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes("admin/accounts?")) {
        return jsonResponse([{ id: "acc1", name: "Acme", type: "team", plan_tier: "pro" }]);
      }
      return jsonResponse([]);
    });
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ accountId: "self1", platformRole: "superadmin" });

    render(<MemoryRouter><AdminConsolePage /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
  });

  it("hides the revoke button for a non-superadmin viewer on the sessions tab", async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes("admin/sessions?")) return jsonResponse([{ jti: "abc123", ttl_seconds: 900 }]);
      return jsonResponse([]);
    });
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ accountId: "self1", platformRole: "superadmin" });

    render(<MemoryRouter><AdminConsolePage /></MemoryRouter>);
    screen.getByRole("button", { name: /sessions/i }).click();

    await waitFor(() => expect(screen.getByText("abc123")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /revoke/i })).toBeInTheDocument();
  });
});