import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CalendarPage } from "./CalendarPage.jsx";
import * as AuthContext from "../../auth/AuthContext.jsx";

function jsonResponse(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 400, json: async () => body, clone() { return this; } });
}

const TODAY_ISO = new Date().toISOString();

function mockCalendarFetch({ scheduled = [], content = [] } = {}) {
  return vi.fn((url) => {
    if (url.includes("scheduler/calendar")) return jsonResponse(scheduled);
    if (url.includes("scheduler/") && url.includes("?scope=")) return Promise.resolve({ ok: true, status: 204, json: async () => ({}) });
    if (url.includes("/content")) return jsonResponse(content);
    return jsonResponse({});
  });
}

describe("CalendarPage", () => {
  it("hides scheduling controls for a member and shows a role hint instead", async () => {
    global.fetch = mockCalendarFetch();
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "member" });

    render(<MemoryRouter><CalendarPage /></MemoryRouter>);

    expect(await screen.findByText(/requires the owner or admin role/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^schedule$/i })).not.toBeInTheDocument();
  });

  it("shows a validation error when scheduling without picking content or a time", async () => {
    global.fetch = mockCalendarFetch();
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "owner" });

    render(<MemoryRouter><CalendarPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole("button", { name: /^schedule$/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /^schedule$/i }));

    expect(await screen.findByText(/pick content and a publish time/i)).toBeInTheDocument();
  });

  it("lets an owner cancel a single occurrence after confirming", async () => {
    const scheduled = [
      { id: "sched1", account_id: "a1", content_id: "c1", has_image: false, publish_at: TODAY_ISO, status: "pending", recurrence_rule: null, recurrence_parent_id: null, created_at: TODAY_ISO },
    ];
    global.fetch = mockCalendarFetch({ scheduled });
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "owner" });

    render(<MemoryRouter><CalendarPage /></MemoryRouter>);
    const eventButton = await screen.findByTestId("scheduled-sched1");
    fireEvent.click(eventButton);

    fireEvent.click(await screen.findByRole("button", { name: /cancel this occurrence/i }));
    expect(await screen.findByText(/cancel this occurrence\?/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^cancel it$/i }));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("scheduler/sched1?scope=single"),
        expect.objectContaining({ method: "DELETE" })
      )
    );
  });

  it("offers a series-wide cancel option only for recurring items", async () => {
    const scheduled = [
      { id: "sched1", account_id: "a1", content_id: "c1", has_image: false, publish_at: TODAY_ISO, status: "pending", recurrence_rule: { freq: "weekly", interval: 1, until: null }, recurrence_parent_id: null, created_at: TODAY_ISO },
    ];
    global.fetch = mockCalendarFetch({ scheduled });
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "admin" });

    render(<MemoryRouter><CalendarPage /></MemoryRouter>);
    fireEvent.click(await screen.findByTestId("scheduled-sched1"));

    expect(await screen.findByRole("button", { name: /cancel entire series/i })).toBeInTheDocument();
  });
});