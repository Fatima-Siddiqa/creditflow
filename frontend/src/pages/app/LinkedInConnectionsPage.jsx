import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { Card } from "../../components/Card.jsx";
import { Button } from "../../components/Button.jsx";
import { ConfirmModal } from "../../components/ConfirmModal.jsx";

export function LinkedInConnectionsPage() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.get("social/linkedin/status");
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not load LinkedIn status.");
      setStatus(data);
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