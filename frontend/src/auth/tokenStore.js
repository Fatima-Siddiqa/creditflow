// Access token lives here, in a plain module-level variable -- never
// localStorage/sessionStorage, per spec §4: "store access token in
// memory". Deliberately outside React state too, so api/client.js (a
// plain fetch wrapper, not a component) can read/refresh it without
// needing hooks. AuthContext mirrors this into React state separately
// so components re-render on change.
let accessToken = null;
let refreshPromise = null;

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

export function getAccessToken() {
  return accessToken;
}

export function setAccessToken(token) {
  accessToken = token;
}

export function clearAccessToken() {
  accessToken = null;
}

export async function refreshAccessToken() {
  // Dedupe concurrent refresh attempts (e.g. several components' fetches
  // all 401 at once) into a single in-flight request.
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const res = await fetch(`${BASE_URL}/api/auth/refresh`, {
      method: "POST",
      credentials: "include", // sends the httpOnly refresh_token cookie
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      accessToken = null;
      throw new Error("refresh_failed");
    }
    const data = await res.json();
    accessToken = data.access_token;
    return accessToken;
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}