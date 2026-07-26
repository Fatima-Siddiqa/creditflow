import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { OnboardingPage } from "./OnboardingPage.jsx";
import * as AuthContext from "../auth/AuthContext.jsx";

function mockFetchOnce(body) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
    clone() { return this; },
  });
}

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ switchAccount: vi.fn(), logout: vi.fn() });
  });

  it("shows the account list when the user belongs to more than one account", async () => {
    mockFetchOnce([
      { account_id: "a1", name: "Individual", type: "individual", role: "owner", plan_tier: "free" },
      { account_id: "a2", name: "Acme Team", type: "team", role: "member", plan_tier: "free" },
    ]);
    render(<MemoryRouter><OnboardingPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Acme Team")).toBeInTheDocument());
  });

  it("shows a setup message when no accounts exist yet", async () => {
    mockFetchOnce([]);
    render(<MemoryRouter><OnboardingPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/setting up/i)).toBeInTheDocument());
  });
});