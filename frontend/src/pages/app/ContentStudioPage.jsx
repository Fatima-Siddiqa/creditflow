import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client.js";
import { getAccessToken } from "../../auth/tokenStore.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { Card } from "../../components/Card.jsx";
import { Button } from "../../components/Button.jsx";
import { TextInput } from "../../components/TextInput.jsx";
import { ConfirmModal } from "../../components/ConfirmModal.jsx";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Mirrors ai-generation-service's settings.allowed_models -- no endpoint
// exposes this list, so it's hardcoded here. Update both places together
// if the service's allow-list ever changes.
const MODELS = [
  { value: "openai/gpt-4o-mini", label: "GPT-4o mini (fast)" },
  { value: "anthropic/claude-3.5-sonnet", label: "Claude 3.5 Sonnet (higher quality)" },
];

const STATUS_STYLES = {
  draft: "bg-gray-100 text-gray-600",
  approved: "bg-sky-100 text-sky-700",
  published: "bg-accent-100 text-accent-700",
};

function StatusBadge({ status }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
}

async function uploadImage(contentId, file) {
  const res = await fetch(`${BASE_URL}/api/content/${contentId}/image`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getAccessToken()}` }, // no Content-Type -- browser sets the multipart boundary
    credentials: "include",
    body: (() => {
      const form = new FormData();
      form.append("file", file);
      return form;
    })(),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error?.message || "Could not upload image.");
  return data;
}

export function ContentStudioPage() {
  const { role } = useAuth();
  const canPublish = role === "owner" || role === "admin";

  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState(MODELS[0].value);
  const [streaming, setStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState("");
  const [jobId, setJobId] = useState(null);
  const [genError, setGenError] = useState(null);

  const [drafts, setDrafts] = useState([]);
  const [listError, setListError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [editing, setEditing] = useState(null); // { id, body }
  const [pendingDelete, setPendingDelete] = useState(null);

  const eventSourceRef = useRef(null);

  const loadDrafts = useCallback(async () => {
    setListError(null);
    try {
      const res = await api.get("content");
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not load content.");
      setDrafts(data);
    } catch (err) {
      setListError(err.message);
    }
  }, []);

  useEffect(() => { loadDrafts(); }, [loadDrafts]);
  useEffect(() => () => eventSourceRef.current?.close(), []); // cleanup on unmount

  const startGeneration = async (e) => {
    e.preventDefault();
    if (!prompt.trim()) return setGenError("Prompt is required.");
    setGenError(null);
    setStreamedText("");
    setStreaming(true);

    try {
      const res = await api.post("ai/generate", { prompt: prompt.trim(), model, content_type: "post" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not start generation.");
      setJobId(data.job_id);

      const es = new EventSource(`${BASE_URL}/api/ai/stream/${data.job_id}?token=${getAccessToken()}`);
      eventSourceRef.current = es;

      es.addEventListener("token", (ev) => setStreamedText((prev) => prev + ev.data));
      es.addEventListener("done", () => {
        es.close();
        setStreaming(false);
        setJobId(null);
        // content-service creates the draft asynchronously off the
        // ai.generation_completed event -- give the consumer a moment,
        // then refresh. The manual "Refresh drafts" button covers it if
        // this fires before the event's been processed.
        setTimeout(loadDrafts, 1500);
      });
      es.addEventListener("error", (ev) => {
        setGenError(ev.data || "Connection lost while generating.");
        es.close();
        setStreaming(false);
        setJobId(null);
      });
    } catch (err) {
      setGenError(err.message);
      setStreaming(false);
    }
  };

  const cancelGeneration = async () => {
    if (!jobId) return;
    try {
      await api.post(`ai/generate/${jobId}/cancel`, {});
    } catch {
      // best-effort -- the stream's own "error"/"done" handler cleans up state
    }
  };

  const saveEdit = async () => {
    if (!editing) return;
    setBusyId(editing.id);
    try {
      const res = await api.patch(`content/${editing.id}`, { body: editing.body });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not save changes.");
      setEditing(null);
      await loadDrafts();
    } catch (err) {
      setListError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleImageChange = async (contentId, file) => {
    if (!file) return;
    setBusyId(contentId);
    try {
      await uploadImage(contentId, file);
      await loadDrafts();
    } catch (err) {
      setListError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const runAction = async (contentId, action) => {
    setBusyId(contentId);
    try {
      const res = await api.post(`content/${contentId}/${action}`, {});
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || `Could not ${action.replace("-", " ")}.`);
      await loadDrafts();
    } catch (err) {
      setListError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setBusyId(pendingDelete);
    try {
      const res = await api.delete(`content/${pendingDelete}`);
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data?.error?.message || "Could not delete content.");
      }
      setPendingDelete(null);
      await loadDrafts();
    } catch (err) {
      setListError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold text-gray-900">Content Studio</h1>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">Generate a post</h2>
        {genError && <p className="mb-2 text-sm text-red-600">{genError}</p>}
        <form onSubmit={startGeneration} className="space-y-3">
          <TextInput
            label="Prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Write a LinkedIn post about..."
            disabled={streaming}
          />
          <div className="flex items-center gap-2">
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={streaming}
              className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
            >
              {MODELS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            {!streaming ? (
              <Button type="submit">Generate</Button>
            ) : (
              <Button type="button" variant="outline" onClick={cancelGeneration}>Cancel</Button>
            )}
          </div>
        </form>

        {(streaming || streamedText) && (
          <div className="mt-4 whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm text-gray-800">
            {streamedText}
            {streaming && <span className="animate-pulse text-brand-500">▍</span>}
          </div>
        )}
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">Drafts &amp; content</h2>
          <Button variant="outline" onClick={loadDrafts}>Refresh</Button>
        </div>
        {listError && <p className="mb-2 text-sm text-red-600">{listError}</p>}
        {drafts.length === 0 && <p className="text-sm text-gray-400">No content yet -- generate a post above.</p>}

        <div className="space-y-3">
          {drafts.map((c) => (
            <div key={c.id} className="rounded-lg border border-gray-100 p-4">
              <div className="mb-2 flex items-center justify-between">
                <StatusBadge status={c.status} />
                <span className="text-xs text-gray-400">{new Date(c.updated_at).toLocaleString()}</span>
              </div>

              {editing?.id === c.id ? (
                <div className="space-y-2">
                  <textarea
                    className="w-full rounded-lg border border-gray-300 p-2 text-sm"
                    rows={4}
                    value={editing.body}
                    onChange={(e) => setEditing({ ...editing, body: e.target.value })}
                  />
                  <div className="flex gap-2">
                    <Button disabled={busyId === c.id} onClick={saveEdit}>Save</Button>
                    <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
                  </div>
                </div>
              ) : (
                <p className="whitespace-pre-wrap text-sm text-gray-700">{c.body}</p>
              )}

              {c.image_url && (
                <img src={`${BASE_URL}${c.image_url}`} alt="" className="mt-2 h-24 rounded-lg object-cover" />
              )}

              <div className="mt-3 flex flex-wrap items-center gap-2">
                {editing?.id !== c.id && (
                  <Button variant="outline" onClick={() => setEditing({ id: c.id, body: c.body })}>Edit</Button>
                )}
                <label className="cursor-pointer rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
                  {c.image_url ? "Replace image" : "Add image"}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => handleImageChange(c.id, e.target.files?.[0])}
                  />
                </label>
                {c.status === "draft" && (
                  <Button disabled={!canPublish || busyId === c.id} onClick={() => runAction(c.id, "approve")}>
                    Approve
                  </Button>
                )}
                {c.status === "approved" && (
                  <Button disabled={!canPublish || busyId === c.id} onClick={() => runAction(c.id, "publish-request")}>
                    Send to publish
                  </Button>
                )}
                <Button variant="danger" disabled={busyId === c.id} onClick={() => setPendingDelete(c.id)}>
                  Delete
                </Button>
              </div>
              {!canPublish && (c.status === "draft" || c.status === "approved") && (
                <p className="mt-1 text-xs text-gray-400">Approve/publish requires the owner or admin role.</p>
              )}
            </div>
          ))}
        </div>
      </Card>

      <ConfirmModal
        open={!!pendingDelete}
        title="Delete this content?"
        description="This removes the draft and all of its versions. This can't be undone."
        confirmLabel="Delete"
        busy={busyId === pendingDelete}
        onCancel={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
      />
    </div>
  );
}