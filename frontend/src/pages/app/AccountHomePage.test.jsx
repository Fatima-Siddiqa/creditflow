import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AccountHomePage } from "./AccountHomePage.jsx";
import * as AuthContext from "../../auth/AuthContext.jsx";

function jsonResponse(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 400, json: async () => body, clone() { return this; } });
}

describe("AccountHomePage", () => {
  it("renders the Owner Dashboard for the owner role", async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes("accounts/acc1")) return jsonResponse({ name: "Acme Team", plan_tier: "pro", seat_count: 3 });
      if (url.includes("credits/balance")) return jsonResponse({ balance: 120 });
      if (url.includes("usage/summary")) return jsonResponse({ total_tokens: 500, period: "2026-07", by_model: [] });
      return jsonResponse({});
    });
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "owner", accountId: "acc1" });

    render(<MemoryRouter><AccountHomePage /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText("Acme Team")).toBeInTheDocument());
    expect(screen.getByText("Credit balance")).toBeInTheDocument();
  });

  it("renders a lightweight welcome view for member/admin roles, without dashboard fetches", async () => {
    global.fetch = vi.fn();
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "member", accountId: "acc1" });

    render(<MemoryRouter><AccountHomePage /></MemoryRouter>);

    expect(screen.getByText(/welcome back/i)).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });
});