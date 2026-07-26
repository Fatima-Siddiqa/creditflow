import { getAccessToken, refreshAccessToken, clearAccessToken } from "../auth/tokenStore.js";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

async function request(path, options = {}, _retried = false) {
  const token = getAccessToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}/api/${path}`, { ...options, headers, credentials: "include" });

  if (res.status === 401 && !_retried) {
    let code = null;
    try {
      const body = await res.clone().json();
      code = body?.error?.code;
    } catch {
      /* non-JSON 401, fall through */
    }
    // Only "token_expired" is the gateway's silent-refresh signal (see
    // api-gateway/app/dependencies.py) -- missing/invalid/session_revoked
    // mean the session is actually dead, don't try to refresh those.
    if (code === "token_expired") {
      try {
        await refreshAccessToken();
        return request(path, options, true);
      } catch {
        clearAccessToken();
      }
    }
  }

  return res;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body: JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: "DELETE" }),
};