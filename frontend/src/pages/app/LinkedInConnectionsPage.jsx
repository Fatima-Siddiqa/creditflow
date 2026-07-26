import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { Card } from "../../components/Card.jsx";
import { Button } from "../../components/Button.jsx";
import { ConfirmModal } from "../../components/ConfirmModal.jsx";

const STATUS_STYLES = {
  pending: "bg-gray-100 text-gray-600",
  publishing: "bg-sky-100 text-sky-700",
  published: "bg-accent-100 text-accent-700",
  failed: "bg-red-100 text-red-600",
};

function StatusBadge({ status }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
}

export function LinkedInConnectionsPage() {
  const [status, setStatus] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [statusRes, jobsRes] = await Promise.all([
        api.get("social/linkedin/status"),
        api.get("social/publish-jobs"),
      ]);
      const [statusData, jobsData] = await Promise.all([statusRes.json(), jobsRes.json()]);
      if (!statusRes.ok) throw new Error(statusData?.error?.message || "Could not load LinkedIn status.");
      setStatus(statusData);
      setJobs(jobsRes.ok ? jobsData : []); // publish history is a nice-to-have -- don't block the page on it
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.get("social/linkedin/connect");
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not start LinkedIn connect.");
      window.location.href = data.authorize_url; // full browser navigation -- LinkedIn's OAuth screen isn't embeddable
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.delete("social/linkedin/disconnect");
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data?.error?.message || "Could not disconnect.");
      }
      setConfirmDisconnect(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold text-gray-900">LinkedIn Connections</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card className="max-w-md">
        {status === null ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : status.connected ? (
          <div className="space-y-3">
            <p className="flex items-center gap-2 text-sm text-gray-700">
              <span className="h-2 w-2 rounded-full bg-accent-500" /> Connected
            </p>
            {status.expires_at && (
              <p className="text-xs text-gray-400">Token refreshes automatically before it expires ({new Date(status.expires_at).toLocaleString()}).</p>
            )}
            <Button variant="danger" disabled={busy} onClick={() => setConfirmDisconnect(true)}>
              Disconnect
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-gray-500">No LinkedIn account connected yet. Connect one to publish scheduled posts.</p>
            <Button disabled={busy} onClick={connect}>Connect LinkedIn</Button>
          </div>
        )}
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">Recent publish activity</h2>
          <Button variant="outline" onClick={load}>Refresh</Button>
        </div>
        {jobs.length === 0 ? (
          <p className="text-sm text-gray-400">Nothing published yet -- schedule an approved post to see it here.</p>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => (
              <div key={job.id} className="flex items-center justify-between border-b border-gray-100 py-2 last:border-0 text-sm">
                <div>
                  <p className="text-gray-700">Content {job.content_id.slice(0, 8)}…</p>
                  <p className="text-xs text-gray-400">
                    {new Date(job.created_at).toLocaleString()}
                    {job.attempt_count > 1 && ` · ${job.attempt_count} attempts`}
                    {job.status === "failed" && job.last_error && ` · ${job.last_error}`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={job.status} />
                  {job.linkedin_post_urn && job.status === "published" && (
                    
                      href={`https://www.linkedin.com/feed/update/${job.linkedin_post_urn}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-brand-600 hover:underline"
                    >
                      View
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <ConfirmModal
        open={confirmDisconnect}
        title="Disconnect LinkedIn?"
        description="Scheduled posts won't be able to publish until you reconnect."
        confirmLabel="Disconnect"
        busy={busy}
        onCancel={() => setConfirmDisconnect(false)}
        onConfirm={disconnect}
      />
    </div>
  );
}