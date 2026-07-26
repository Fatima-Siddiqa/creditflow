import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ContentStudioPage } from "./ContentStudioPage.jsx";
import * as AuthContext from "../../auth/AuthContext.jsx";

class MockEventSource {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.listeners = {};
    MockEventSource.instances.push(this);
  }
  addEventListener(type, cb) {
    (this.listeners[type] ??= []).push(cb);
  }
  close() { this.closed = true; }
  emit(type, data) {
    (this.listeners[type] || []).forEach((cb) => cb({ data }));
  }
}

function jsonResponse(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 400, json: async () => body, clone() { return this; } });
}

const NO_DRAFTS = () => jsonResponse([]);

beforeEach(() => {
  MockEventSource.instances = [];
  global.EventSource = MockEventSource;
});

describe("ContentStudioPage", () => {
  it("loads and displays existing drafts on mount", async () => {
    global.fetch = vi.fn(() =>
      jsonResponse([
        { id: "c1", account_id: "a1", created_by_user_id: "u1", status: "draft", image_url: null, current_version_id: "v1", body: "Hello world", created_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-01T00:00:00Z" },
      ])
    );
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "owner" });

    render(<MemoryRouter><ContentStudioPage /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText("Hello world")).toBeInTheDocument());
    expect(screen.getByText("draft")).toBeInTheDocument();
  });

  it("shows a validation error and does not call the generate API when the prompt is empty", async () => {
    global.fetch = vi.fn(NO_DRAFTS);
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "owner" });

    render(<MemoryRouter><ContentStudioPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/no content yet/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /^generate$/i }));

    expect(await screen.findByText(/prompt is required/i)).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalledWith(expect.stringContaining("ai/generate"), expect.anything());
  });

  it("streams tokens live and returns to the idle state when the stream finishes", async () => {
    global.fetch = vi.fn((url, options = {}) => {
      if (url.includes("ai/generate")) {
        return jsonResponse({ job_id: "job1", status: "RUNNING", model: "openai/gpt-4o-mini" });
      }
      return NO_DRAFTS();
    });
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "owner" });

    render(<MemoryRouter><ContentStudioPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/no content yet/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/prompt/i), { target: { value: "Write about AI" } });
    fireEvent.click(screen.getByRole("button", { name: /^generate$/i }));

    await waitFor(() => expect(MockEventSource.instances.length).toBe(1));
    const es = MockEventSource.instances[0];
    expect(es.url).toContain("job1");

    es.emit("token", "Hello ");
    es.emit("token", "world");
    await waitFor(() => expect(screen.getByText("Hello world")).toBeInTheDocument());

    es.emit("done");
    await waitFor(() => expect(screen.getByRole("button", { name: /^generate$/i })).toBeInTheDocument());
    expect(es.closed).toBe(true);
  });

  it("surfaces a stream error and stops streaming without leaving the job hanging", async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes("ai/generate")) return jsonResponse({ job_id: "job1", status: "RUNNING", model: "openai/gpt-4o-mini" });
      return NO_DRAFTS();
    });
    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "owner" });

    render(<MemoryRouter><ContentStudioPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/no content yet/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/prompt/i), { target: { value: "Write about AI" } });
    fireEvent.click(screen.getByRole("button", { name: /^generate$/i }));

    await waitFor(() => expect(MockEventSource.instances.length).toBe(1));
    MockEventSource.instances[0].emit("error", "OpenRouter timed out");

    expect(await screen.findByText(/openrouter timed out/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^generate$/i })).toBeInTheDocument();
  });

  it("disables approve/publish actions for a member but not for an owner", async () => {
    const draft = { id: "c1", account_id: "a1", created_by_user_id: "u1", status: "draft", image_url: null, current_version_id: "v1", body: "Draft body", created_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-01T00:00:00Z" };
    global.fetch = vi.fn(() => jsonResponse([draft]));

    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "member" });
    const { unmount } = render(<MemoryRouter><ContentStudioPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole("button", { name: /approve/i })).toBeDisabled());
    unmount();

    vi.spyOn(AuthContext, "useAuth").mockReturnValue({ role: "owner" });
    render(<MemoryRouter><ContentStudioPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole("button", { name: /approve/i })).not.toBeDisabled());
  });
});