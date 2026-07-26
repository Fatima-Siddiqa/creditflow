import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "../api/client.js";
import { setAccessToken, clearAccessToken, refreshAccessToken } from "./tokenStore.js";

const AuthContext = createContext(null);

function decodeClaims(token) {
  if (!token) return null;
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [claims, setClaims] = useState(null);
  const [initializing, setInitializing] = useState(true);

  const applyToken = useCallback((token) => {
    setAccessToken(token);
    setClaims(decodeClaims(token));
  }, []);

  useEffect(() => {
    // On first load, the access token is gone (memory-only, survives
    // nothing) -- try a silent refresh against the httpOnly cookie to
    // pick a session back up, per spec §4's JWT handling requirement.
    (async () => {
      try {
        const token = await refreshAccessToken();
        applyToken(token);
      } catch {
        clearAccessToken();
        setClaims(null);
      } finally {
        setInitializing(false);
      }
    })();
  }, [applyToken]);

  const login = useCallback(
    async (email, password) => {
      const res = await api.post("auth/login", { email, password });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.error?.message || data?.error?.message || "Login failed.");
      applyToken(data.access_token);
      return data;
    },
    [applyToken]
  );

  const logout = useCallback(async () => {
    try {
      await api.post("auth/logout", {});
    } catch {
      // best-effort -- clear local state regardless of network outcome
    }
    clearAccessToken();
    setClaims(null);
  }, []);

  // Used by the account switcher (next branch) -- re-scopes the access
  // token without touching the refresh cookie at all.
  const switchAccount = useCallback((accessToken) => {
    applyToken(accessToken);
  }, [applyToken]);

  const value = {
    isAuthenticated: !!claims,
    initializing,
    userId: claims?.sub ?? null,
    accountId: claims?.account_id ?? null,
    role: claims?.role ?? null,
    platformRole: claims?.platform_role ?? null,
    login,
    logout,
    switchAccount,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}