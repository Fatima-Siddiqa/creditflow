import { useEffect, useState, useCallback } from "react";
import { api } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { Card } from "../../components/Card.jsx";
import { Button } from "../../components/Button.jsx";
import { TextInput } from "../../components/TextInput.jsx";
import { ConfirmModal } from "../../components/ConfirmModal.jsx";

const ROLES = ["owner", "admin", "member"];

export function TeamManagementPage() {
  const { accountId, userId } = useAuth();
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [inviteError, setInviteError] = useState(null);
  const [error, setError] = useState(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [busy, setBusy] = useState(false);
  const [pendingRemoval, setPendingRemoval] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [mRes, iRes] = await Promise.all([
        api.get(`accounts/${accountId}/members`),
        api.get(`accounts/${accountId}/invites`),
      ]);
      const [mData, iData] = await Promise.all([mRes.json(), iRes.json()]);
      if (!mRes.ok) throw new Error(mData?.error?.message || "Could not load members.");
      setMembers(mData);
      setInvites(iRes.ok ? iData : []);
    } catch (err) {
      setError(err.message);
    }
  }, [accountId]);

  useEffect(() => { load(); }, [load]);

  const sendInvite = async (e) => {
    e.preventDefault();
    const email = inviteEmail.trim();
    if (!email) return setError("Email is required.");

    // Check the already-loaded pending invites before hitting the API,
    // so a re-invite of the same email surfaces as a clear inline
    // message instead of firing off another POST. The backend also
    // safely dedupes (rotates the existing row's token/expiry rather
    // than creating a duplicate) if this client-side check is bypassed
    // by a stale `invites` list.
    const pending = invites.find((i) => i.email.toLowerCase() === email.toLowerCase());
    if (pending) return setInviteError(`Invitation to ${email} was already sent and is pending.`);

    setBusy(true);
    setInviteError(null);
    try {
      const res = await api.post(`accounts/${accountId}/invites`, { email, role: inviteRole });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not send invite.");
      setInviteEmail("");
      await load();
    } catch (err) {
      setInviteError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const resendInvite = async (invite) => {
    setError(null);
    try {
      const res = await api.post(`accounts/${accountId}/invites/${invite.id}/resend`);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not resend invite.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const changeRole = async (member, role) => {
    setError(null);
    try {
      const res = await api.patch(`accounts/${accountId}/members/${member.user_id}`, { role });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || "Could not update role.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const confirmRemove = async () => {
    if (!pendingRemoval) return;
    setBusy(true);
    try {
      const res = await api.delete(`accounts/${accountId}/members/${pendingRemoval.user_id}`);
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data?.error?.message || "Could not remove member.");
      }
      setPendingRemoval(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold text-gray-900">Team management</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">Members</h2>
        <div className="space-y-2">
          {members.map((m) => (
            <div key={m.user_id} className="flex items-center justify-between border-b border-gray-100 py-2 last:border-0">
              <div className="text-sm">
                <p className="font-medium text-gray-800">{m.email ?? m.user_id}</p>
                <p className="text-xs text-gray-400">joined {new Date(m.joined_at).toLocaleDateString()}</p>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={m.role}
                  onChange={(e) => changeRole(m, e.target.value)}
                  disabled={m.user_id === userId}
                  className="rounded-lg border border-gray-300 px-2 py-1 text-sm"
                >
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
                <Button variant="danger" disabled={m.user_id === userId} onClick={() => setPendingRemoval(m)}>
                  Remove
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {invites.length > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">Pending invites</h2>
          <div className="space-y-1 text-sm text-gray-600">
            {invites.map((i) => (
              <div key={i.id} className="flex items-center justify-between">
                <span>{i.email}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">{i.role} · expires {new Date(i.expires_at).toLocaleDateString()}</span>
                  <Button variant="outline" onClick={() => resendInvite(i)}>Resend</Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">Invite a member</h2>
        {inviteError && <p className="mb-2 text-sm text-red-600">{inviteError}</p>}
        <form onSubmit={sendInvite} className="flex flex-wrap gap-2">
          <TextInput type="email" placeholder="Email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} className="flex-1" />
          <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-2 text-sm">
            <option value="member">member</option>
            <option value="admin">admin</option>
          </select>
          <Button disabled={busy}>Send invite</Button>
        </form>
      </Card>

      <ConfirmModal
        open={!!pendingRemoval}
        title="Remove member?"
        description={pendingRemoval ? `${pendingRemoval.email ?? pendingRemoval.user_id} will lose access to this account immediately.` : ""}
        confirmLabel="Remove"
        busy={busy}
        onCancel={() => setPendingRemoval(null)}
        onConfirm={confirmRemove}
      />
    </div>
  );
}