// ============================================================
// EXTENSION — hooks/useExtApi.js
// NEW hook for extension endpoints (/api/ext/*)
// Does NOT modify or replace existing hooks/useApi.js
// ============================================================

import { useState, useEffect, useRef } from "react";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:5000";
const EXT_BASE = `${BASE}/api/ext`;

// -------------------------------------------------------
// Core fetcher — extension version
// -------------------------------------------------------
export function useExtApi(path, params = {}, deps = []) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const abortRef              = useRef(null);

  useEffect(() => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    const url = new URL(`${EXT_BASE}${path}`);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });

    fetch(url.toString(), { signal: controller.signal })
      .then((r) => r.json())
      .then((json) => {
        if (!controller.signal.aborted) {
          setData(json);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error };
}

// -------------------------------------------------------
// One-shot POST helper
// -------------------------------------------------------
export async function extPost(path, body = {}) {
  const res = await fetch(`${EXT_BASE}${path}`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  return res.json();
}

// -------------------------------------------------------
// One-shot DELETE helper
// -------------------------------------------------------
export async function extDelete(path) {
  const res = await fetch(`${EXT_BASE}${path}`, { method: "DELETE" });
  return res.json();
}

// -------------------------------------------------------
// One-shot GET helper (no reactive state)
// -------------------------------------------------------
export async function extGet(path, params = {}) {
  const url = new URL(`${EXT_BASE}${path}`);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  });
  const res = await fetch(url.toString());
  return res.json();
}
