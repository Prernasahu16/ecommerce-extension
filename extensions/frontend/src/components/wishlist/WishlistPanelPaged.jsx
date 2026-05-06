/* ============================================================
   EXTENSION — components/wishlist/WishlistPanelPaged.jsx
   Adds pagination to saved + wishlist.
   Renders INSTEAD of WishlistPanel when tab count > PAGE_SIZE.
   WishlistPanel.jsx is NOT modified.
   ============================================================ */

import { useState, useEffect, useCallback } from "react";
import "./WishlistPanel.css";     // reuse existing styles
import "./WishlistPanelPaged.css"; // only new styles here

const BASE     = (import.meta.env.VITE_API_URL || "http://localhost:5000") + "/api/ext";
const PG_SIZE  = 20;

function getSessionId() {
  let id = localStorage.getItem("ext_session_id");
  if (!id) {
    id = "sess_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("ext_session_id", id);
  }
  return id;
}

export default function WishlistPanelPaged() {
  const [tab,      setTab]      = useState("wishlist");
  const [page,     setPage]     = useState(1);
  const [data,     setData]     = useState(null);   // { data, total, pages }
  const [loading,  setLoading]  = useState(false);
  const sessionId = getSessionId();

  const load = useCallback(async (t = tab, p = page) => {
    setLoading(true);
    try {
      const endpoint = t === "wishlist" ? "wishlist" : "saved";
      const res  = await fetch(`${BASE}/${endpoint}/${sessionId}/page?page=${p}&limit=${PG_SIZE}`);
      const json = await res.json();
      if (json.success) setData(json);
    } catch (e) {
      console.error("WishlistPanelPaged load error:", e);
    } finally {
      setLoading(false);
    }
  }, [tab, page, sessionId]);

  useEffect(() => { load(tab, 1); setPage(1); }, [tab]);
  useEffect(() => { load(tab, page); },          [page]);

  const switchTab = (t) => { setTab(t); setData(null); };

  const handleRemove = async (item) => {
    const endpoint = tab === "wishlist" ? "wishlist" : "saved";
    const pid      = item.ext_product_id;
    await fetch(`${BASE}/${endpoint}/${sessionId}/${pid}`, { method: "DELETE" });
    // Reload current page; if page becomes empty go back one
    const newTotal = (data?.total || 1) - 1;
    const maxPage  = Math.max(1, Math.ceil(newTotal / PG_SIZE));
    const newPage  = Math.min(page, maxPage);
    if (newPage !== page) setPage(newPage);
    else load(tab, page);
  };

  const items      = data?.data || [];
  const totalPages = data?.pages || 1;
  const total      = data?.total || 0;

  return (
    <div className="wl-root wlp-root">
      <div className="wl-header">
        <span className="wl-badge">NEW</span>
        <h2 className="wl-title">My Lists</h2>
        <p className="wl-subtitle">Save products and track your wishlist across sessions</p>
      </div>

      {/* Tabs */}
      <div className="wl-tabs">
        {["wishlist","saved"].map(t => (
          <button key={t}
            className={`wl-tab ${tab === t ? "wl-tab-active" : ""}`}
            onClick={() => switchTab(t)}>
            {t === "wishlist" ? "❤️ Wishlist" : "🔖 Saved"}
            {data && tab === t && total > 0 && <span className="wl-tab-count">{total}</span>}
          </button>
        ))}
        <button className="wl-refresh-btn" onClick={() => load(tab, page)} disabled={loading}>
          {loading ? "…" : "↺"}
        </button>
      </div>

      {loading ? (
        <div className="wl-loading"><span className="wl-spinner" /> Loading…</div>
      ) : items.length === 0 ? (
        <div className="wl-empty">
          <div className="wl-empty-icon">{tab === "wishlist" ? "❤️" : "🔖"}</div>
          <p>Your {tab} is empty.</p>
        </div>
      ) : (
        <>
          <div className="wl-list">
            {items.map(item => (
              <PagedItem key={item.wish_id || item.save_id} item={item} tab={tab} onRemove={() => handleRemove(item)} />
            ))}
          </div>

          {/* Pagination controls */}
          {totalPages > 1 && (
            <div className="wlp-pagination">
              <button className="wlp-pg-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
              <span className="wlp-pg-info">Page {page} / {totalPages} · {total} items</span>
              <button className="wlp-pg-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next →</button>
            </div>
          )}
        </>
      )}

      <div className="wl-session-note">
        Session: <code className="wl-session-id">{sessionId.slice(0, 20)}…</code>
      </div>
    </div>
  );
}

function PagedItem({ item, tab, onRemove }) {
  return (
    <div className="wl-item">
      <div className="wl-item-main">
        <p className="wl-item-name">{item.product_name || "Unknown Product"}</p>
        <div className="wl-item-meta">
          {item.price     && <span className="wl-item-price">${parseFloat(item.price).toFixed(2)}</span>}
          {item.rating    && <span className="wl-item-rating">★ {parseFloat(item.rating).toFixed(1)}</span>}
          {item.source    && <span className="wl-item-source">{item.source}</span>}
          {item.advanced_value_score && <span className="wl-item-muted">Score: {parseFloat(item.advanced_value_score).toFixed(3)}</span>}
        </div>

        {/* Price drop indicator for wishlist */}
        {tab === "wishlist" && item.target_price && (
          <p className={`wl-target ${item.target_reached ? "wl-target-hit" : ""}`}>
            {item.target_reached
              ? `✅ Target reached! (was $${parseFloat(item.target_price).toFixed(2)})`
              : `🎯 Target: $${parseFloat(item.target_price).toFixed(2)}`}
          </p>
        )}

        {tab === "saved" && item.note && <p className="wl-item-note">📝 {item.note}</p>}
        <p className="wl-item-date">
          Added: {new Date(item.added_at || item.saved_at).toLocaleDateString()}
        </p>
      </div>
      <button className="wl-remove-btn" onClick={onRemove} title="Remove">✕</button>
    </div>
  );
}
