// ============================================================
// EXTENSION — hooks/useAuth.js
// JWT auth state manager with localStorage session fallback.
// Exposes: user, token, login(), register(), logout(), isAuthed
// Works alongside existing useExtApi.js — no conflicts.
// ============================================================

import { useState, useEffect, useCallback, createContext, useContext } from "react";

const BASE = (import.meta.env.VITE_API_URL || "http://localhost:5000") + "/api/ext";

const TOKEN_KEY   = "ext_jwt_token";
const USER_KEY    = "ext_user_data";
const SESSION_KEY = "ext_session_id";

// -------------------------------------------------------
// Context — wrap <AuthProvider> around <ExtensionHub>
// -------------------------------------------------------
export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const auth = _useAuthState();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

// -------------------------------------------------------
// Core state — can also be used standalone without context
// -------------------------------------------------------
export function _useAuthState() {
  const [user,    setUser]    = useState(() => {
    try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; }
  });
  const [token,   setToken]   = useState(() => localStorage.getItem(TOKEN_KEY) || null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const isAuthed   = Boolean(token && user);
  const sessionId  = localStorage.getItem(SESSION_KEY) || "anon";

  // Persist on change
  useEffect(() => {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else       localStorage.removeItem(TOKEN_KEY);
  }, [token]);

  useEffect(() => {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    else      localStorage.removeItem(USER_KEY);
  }, [user]);

  // Auto-refresh token 5 min before expiry
  useEffect(() => {
    if (!token) return;
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      const msLeft  = payload.exp * 1000 - Date.now() - 5 * 60 * 1000;
      if (msLeft <= 0) { logout(); return; }
      const t = setTimeout(refresh, msLeft);
      return () => clearTimeout(t);
    } catch { /* non-standard token format */ }
  }, [token]);

  const _post = async (path, body) => {
    const res = await fetch(`${BASE}${path}`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
    return res.json();
  };

  const _authGet = async (path) => {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.json();
  };

  const register = useCallback(async (email, password, displayName = "") => {
    setLoading(true); setError(null);
    try {
      const data = await _post("/auth/register", { email, password, display_name: displayName });
      if (!data.success) { setError(data.error); return { success: false, error: data.error }; }
      setToken(data.data.token);
      setUser({ user_id: data.data.user_id, email: data.data.email, display_name: data.data.display_name });
      await _linkSession(data.data.token);
      return { success: true };
    } catch (e) {
      setError(e.message);
      return { success: false, error: e.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (email, password) => {
    setLoading(true); setError(null);
    try {
      const data = await _post("/auth/login", { email, password });
      if (!data.success) { setError(data.error); return { success: false, error: data.error }; }
      setToken(data.data.token);
      setUser({ user_id: data.data.user_id, email: data.data.email, display_name: data.data.display_name, role: data.data.role });
      await _linkSession(data.data.token);
      return { success: true };
    } catch (e) {
      setError(e.message);
      return { success: false, error: e.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setError(null);
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.success) setToken(data.data.token);
      else logout();
    } catch { logout(); }
  }, [token]);

  // Link session saves/wishlist to real user after auth
  const _linkSession = async (jwt) => {
    try {
      await fetch(`${BASE}/auth/link-session`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${jwt}` },
        body:    JSON.stringify({ session_id: sessionId }),
      });
    } catch { /* non-critical */ }
  };

  // Auth header helper for components
  const authHeaders = token
    ? { Authorization: `Bearer ${token}`, "X-Session-Id": sessionId }
    : { "X-Session-Id": sessionId };

  return { user, token, loading, error, isAuthed, sessionId, authHeaders, login, register, logout, refresh };
}
