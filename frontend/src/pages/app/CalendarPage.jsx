import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { Card } from "../../components/Card.jsx";
import { Button } from "../../components/Button.jsx";
import { ConfirmModal } from "../../components/ConfirmModal.jsx";

const DAY_MS = 24 * 60 * 60 * 1000;
const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function startOfGrid(d) { const s = startOfMonth(d); return new Date(s.getTime() - s.getDay() * DAY_MS); }
function toLocalInputValue(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function dateKey(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const STATUS_STYLES = {
  pending: "bg-sky-100 text-sky-700",
  fired: "bg-accent-100 text-accent-700",
  cancelled: "bg-gray-100 text-gray-400 line-through",
};

export function CalendarPage() {
  const { role } = useAuth();
  const canSchedule = role === "owner" || role === "admin";

  const [month, setMonth] = useState(startOfMonth(new Date()));
  const [scheduled, setScheduled] = useState([]);
  const [approvedContent, setApprovedContent] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const [selectedContentId, setSelectedContentId] = useState("");
  const [publishAt, setPublishAt] = useState("");
  const [freq, setFreq] = useState("none");
  const [interval, setIntervalValue] = useState(1);
  const [until, setUntil] = useState("");

  const [selected, setSelected] = useState(null); // a scheduled_post row
  const [rescheduleAt, setRescheduleAt] = useState("");
  const [cancelScope, setCancelScope] = useState(null); // "single" | "series"

  const gridStart = useMemo(() => startOfGrid(month), [month]);
  const gridEnd = useMemo(() => new Date(gridStart.getTime() + 42 * DAY_MS), [gridStart]);
  const days = useMemo(
    () => Array.from({ length: 42 }, (_, i) => new Date(gridStart.getTime() + i * DAY_MS)),
    [gridStart]
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const [schedRes, contentRes] = await Promise.all([
        api.get(`scheduler/calendar?from=${gridStart.toISOString()}&to=${gridEnd.toISOString()}`),
        api.get("content"),
      ]);
      const [schedData, contentData] = await Promise.all([schedRes.json(), contentRes.json()]);
      if (!schedRes.ok) throw new Error(schedData?.error?.message || "Could not load calendar.");
      setScheduled(schedData);
      setApprovedContent(contentRes.ok ? contentData.filter((c) => c.status === "approved") : []);
    } catch (err) {
      setError(err.message);
    }
  }, [gridStart, gridEnd]);

  useEffect(() => { load(); }, [load]);

  const eventsByDay = useMemo(() => {
    const map = {};
    for (const row of scheduled) {
      const key = dateKey(new Date(row.publish_at));
      (map[key] ??= []).push(row);
    }
    return map;
  }, [scheduled]);

  const submitSchedule = async (e) => {
    e.preventDefault();
    if (!selectedContentId || !publishAt) return setError("Pick content and a publish time.");
    setBusy(true);
    setError(null);
    try {
      const body = {
        content_id: selectedContentId,
        publish_at: new Date(publishAt).toISOString(),
        recurrence_rule: freq === "none" ? undefined : { freq, interval: Number(interval) || 1, until: until || undefined },
      };
      const res = await api.post("scheduler", body);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not schedule this post.");
      setSelectedContentId(""); setPublishAt(""); setFreq("none"); setIntervalValue(1); setUntil("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const openEvent = (row) => {
    setSelected(row);
    setRescheduleAt(toLocalInputValue(row.publish_at));
    setCancelScope(null);
  };

  const saveReschedule = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.patch(`scheduler/${selected.id}/reschedule`, { publish_at: new Date(rescheduleAt).toISOString() });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not reschedule.");
      setSelected(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const confirmCancel = async () => {
    if (!selected || !cancelScope) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.delete(`scheduler/${selected.id}?scope=${cancelScope}`);
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data?.error?.message || "Could not cancel.");
      }
      setSelected(null);
      setCancelScope(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-900">Calendar</h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}>‹</Button>
          <span className="text-sm font-medium text-gray-700">
            {month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
          </span>
          <Button variant="outline" onClick={() => setMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}>›</Button>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg bg-gray-100 text-xs">
          {WEEKDAY_LABELS.map((w) => (
            <div key={w} className="bg-white p-2 text-center font-medium text-gray-400">{w}</div>
          ))}
          {days.map((d) => {
            const key = dateKey(d);
            const inMonth = d.getMonth() === month.getMonth();
            return (
              <div key={key} className={`min-h-[6.5rem] bg-white p-1.5 ${inMonth ? "" : "bg-gray-50 text-gray-300"}`}>
                <p className="mb-1 text-right text-xs">{d.getDate()}</p>
                <div className="space-y-1">
                  {(eventsByDay[key] ?? []).map((ev) => (
                    <button
                      key={ev.id}
                      data-testid={`scheduled-${ev.id}`}
                      onClick={() => openEvent(ev)}
                      className={`block w-full truncate rounded px-1.5 py-0.5 text-left text-[11px] ${STATUS_STYLES[ev.status] ?? "bg-gray-100"}`}
                    >
                      {new Date(ev.publish_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                      {ev.recurrence_rule && " ↻"}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {canSchedule ? (
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">Schedule approved content</h2>
          {approvedContent.length === 0 && (
            <p className="text-sm text-gray-400">No approved content yet -- approve a draft in the Content Studio first.</p>
          )}
          <form onSubmit={submitSchedule} className="flex flex-wrap items-end gap-2">
            <select
              value={selectedContentId}
              onChange={(e) => setSelectedContentId(e.target.value)}
              className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
            >
              <option value="">Select content…</option>
              {approvedContent.map((c) => (
                <option key={c.id} value={c.id}>{c.body.slice(0, 40)}{c.body.length > 40 ? "…" : ""}</option>
              ))}
            </select>
            <input
              type="datetime-local"
              value={publishAt}
              onChange={(e) => setPublishAt(e.target.value)}
              className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
            />
            <select value={freq} onChange={(e) => setFreq(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-2 text-sm">
              <option value="none">One-off</option>
              <option value="daily">Repeats daily</option>
              <option value="weekly">Repeats weekly</option>
              <option value="monthly">Repeats monthly</option>
            </select>
            {freq !== "none" && (
              <>
                <input
                  type="number" min="1" value={interval}
                  onChange={(e) => setIntervalValue(e.target.value)}
                  className="w-16 rounded-lg border border-gray-300 px-2 py-2 text-sm"
                  title="Every N periods"
                />
                <input
                  type="date" value={until}
                  onChange={(e) => setUntil(e.target.value)}
                  className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
                  title="Repeat until"
                />
              </>
            )}
            <Button disabled={busy}>Schedule</Button>
          </form>
        </Card>
      ) : (
        <p className="text-sm text-gray-400">Scheduling requires the owner or admin role.</p>
      )}

      {selected && (
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900">
              Scheduled item {selected.recurrence_rule && <span className="text-gray-400">(part of a recurring series)</span>}
            </h2>
            <Button variant="outline" onClick={() => setSelected(null)}>Close</Button>
          </div>
          {canSchedule && selected.status === "pending" ? (
            <div className="flex flex-wrap items-end gap-2">
              <input
                type="datetime-local"
                value={rescheduleAt}
                onChange={(e) => setRescheduleAt(e.target.value)}
                className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
              />
              <Button disabled={busy} onClick={saveReschedule}>Save new time</Button>
              <Button variant="danger" disabled={busy} onClick={() => setCancelScope("single")}>Cancel this occurrence</Button>
              {selected.recurrence_rule && (
                <Button variant="danger" disabled={busy} onClick={() => setCancelScope("series")}>Cancel entire series</Button>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-500">Status: {selected.status}</p>
          )}
        </Card>
      )}

      <ConfirmModal
        open={!!cancelScope}
        title={cancelScope === "series" ? "Cancel the whole series?" : "Cancel this occurrence?"}
        description={
          cancelScope === "series"
            ? "This cancels every future pending occurrence of this recurring post."
            : "This cancels only this one occurrence; the rest of the series (if any) continues."
        }
        confirmLabel="Cancel it"
        busy={busy}
        onCancel={() => setCancelScope(null)}
        onConfirm={confirmCancel}
      />
    </div>
  );
}