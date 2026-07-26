import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LinkedInConnectionsPage } from "./LinkedInConnectionsPage.jsx";

function jsonResponse(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 400, json: async () => body, clone() { return this; } });
}

beforeEach(() => {
  delete window.location;
  window.location = { href: "" }; // avoid jsdom's "not implemented: navigation" error on a real assignment
});

describe("LinkedInConnectionsPage", () => {
  it("starts the OAuth redirect using the authorize_url returned by the backend", async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes("linkedin/status")) return jsonResponse({ connected: false, expires_at: null });
      if (url.includes("publish-jobs")) return jsonResponse([]);
      if (url.includes("linkedin/connect")) return jsonResponse({ authorize_url: "https://www.linkedin.com/oauth/v2/authorization?foo=bar" });
      return jsonResponse({});
    });

    render(<MemoryRouter><LinkedInConnectionsPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /connect linkedin/i }));

    await waitFor(() => expect(window.location.href).toBe("https://www.linkedin.com/oauth/v2/authorization?foo=bar"));
  });

  it("shows connection status and recent publish activity when connected", async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes("linkedin/status")) return jsonResponse({ connected: true, expires_at: "2026-08-01T00:00:00Z" });
      if (url.includes("publish-jobs")) {
        return jsonResponse([
          { id: "job1", scheduled_post_id: "sched1", content_id: "c1234567890", status: "published", attempt_count: 1, last_error: null, linkedin_post_urn: "urn:li:share:1", created_at: "2026-07-20T00:00:00Z" },
        ]);
      }
      return jsonResponse({});
    });

    render(<MemoryRouter><LinkedInConnectionsPage /></MemoryRouter>);

    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(await screen.findByText("published")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view/i })).toHaveAttribute("href", expect.stringContaining("urn:li:share:1"));
  });

  it("requires confirmation before disconnecting", async () => {
    let connected = true;
    global.fetch = vi.fn((url, options = {}) => {
      if (url.includes("linkedin/status")) return jsonResponse({ connected, expires_at: null });
      if (url.includes("publish-jobs")) return jsonResponse([]);
      if (url.includes("linkedin/disconnect") && options.method === "DELETE") {
        connected = false;
        return jsonResponse({ status: "disconnected" });
      }
      return jsonResponse({});
    });

    render(<MemoryRouter><LinkedInConnectionsPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /^disconnect$/i }));

    expect(await screen.findByText(/disconnect linkedin\?/i)).toBeInTheDocument();

    const disconnectButtons = screen.getAllByRole("button", { name: /^disconnect$/i });
    fireEvent.click(disconnectButtons[disconnectButtons.length - 1]); // the modal's confirm button

    await waitFor(() => expect(screen.getByText(/connect one to publish/i)).toBeInTheDocument());
  });
});