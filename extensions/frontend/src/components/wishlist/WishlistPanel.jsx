/* ============================================================
   EXTENSION — components/wishlist/WishlistPanel.jsx
   Wishlist + Saved panels.  Uses ext_product_id (correct field).
   Session stored in localStorage — no auth required.
   Does NOT modify any existing component.
   ============================================================ */

import { useState, useEffect } from "react";
import "./WishlistPanel.css";

const BASE = (import.meta.env.VITE_API_URL || "http://localhost:5000") + "/api/ext";

export function getSessionId() {
  let id = localStorage.getItem("ext_session_id");
  if (!id) {
    id = "sess_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("ext_session_id", id);
  }
  return id;
}

/* Exported helpers so SearchResultCard / ComparisonView can call them */
export async function saveProduct(ext_product_id, note = "") {
  const res = await fetch(`${BASE}/saved/${getSessionId()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ext_product_id, note }),
  });
  return res.json();
}

export async function addToWishlist(ext_product_id, target_price = null) {
  const res = await fetch(`${BASE}/wishlist/${getSessionId()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ext_product_id, target_price }),
  });
  return res.json();
}

export default function WishlistPanel() {
  const [tab,      setTab]      = useState("wishlist");
  const [wishlist, setWishlist] = useState([]);
  const [saved,    setSaved]    = useState([]);
  const [loading,  setLoading]  = useState(false);
  const sessionId = getSessionId();

  const load = async () => {
    setLoading(true);
    try {
      const [wRes, sRes] = await Promise.all([
        fetch(`${BASE}/wishlist/${sessionId}`).then(r => r.json()),
        fetch(`${BASE}/saved/${sessionId}`).then(r => r.json()),
      ]);
      if (wRes.success) setWishlist(wRes.data || []);
      if (sRes.success) setSaved(sRes.data || []);
    } catch (e) {
      console.error("Wishlist load error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const removeWishlist = async (ext_product_id) => {
    await fetch(`${BASE}/wishlist/${sessionId}/${ext_product_id}`, { method: "DELETE" });
    setWishlist(prev => prev.filter(i => i.ext_product_id !== ext_product_id));
  };

  const removeSaved = async (ext_product_id) => {
    await fetch(`${BASE}/saved/${sessionId}/${ext_product_id}`, { method: "DELETE" });
    setSaved(prev => prev.filter(i => i.ext_product_id !== ext_product_id));
  };

  const items    = tab === "wishlist" ? wishlist : saved;
  const onRemove = tab === "wishlist"
    ? (item) => removeWishlist(item.ext_product_id)
    : (item) => removeSaved(item.ext_product_id);

  return (
    <div className="wl-root">
      <div className="wl-header">
        <span className="wl-badge">NEW</span>
        <h2 className="wl-title">My Lists</h2>
        <p className="wl-subtitle">Save products and track your wishlist across sessions</p>
      </div>

      <div className="wl-tabs">
        <button className={`wl-tab ${tab === "wishlist" ? "wl-tab-active" : ""}`}
          onClick={() => setTab("wishlist")}>
          ❤️ Wishlist
          {wishlist.length > 0 && <span className="wl-tab-count">{wishlist.length}</span>}
        </button>
        <button className={`wl-tab ${tab === "saved" ? "wl-tab-active" : ""}`}
          onClick={() => setTab("saved")}>
          🔖 Saved
          {saved.length > 0 && <span className="wl-tab-count">{saved.length}</span>}
        </button>
        <button className="wl-refresh-btn" onClick={load} disabled={loading}>
          {loading ? "…" : "↺"}
        </button>
      </div>

      <div className="wl-tip">
        <span className="wl-tip-icon">💡</span>
        Use the <strong>❤️</strong> and <strong>🔖</strong> buttons on any search result
        or comparison card to add products here. Your lists persist across visits.
      </div>

      {loading ? (
        <div className="wl-loading">
          <span className="wl-spinner" /> Loading your {tab}…
        </div>
      ) : items.length === 0 ? (
        <div className="wl-empty">
          <div className="wl-empty-icon">{tab === "wishlist" ? "❤️" : "🔖"}</div>
          <p>Your {tab} is empty.</p>
          <p>Search for products and save them here.</p>
        </div>
      ) : (
        <div className="wl-list">
          {items.map(item => (
            <WishlistItem
              key={item.wish_id || item.save_id}
              item={item}
              tab={tab}
              onRemove={() => onRemove(item)}
            />
          ))}
        </div>
      )}

      <div className="wl-session-note">
        Session: <code className="wl-session-id">{sessionId.slice(0, 20)}…</code>
      </div>
    </div>
  );
}

function WishlistItem({ item, tab, onRemove }) {
  return (
    <div className="wl-item">
      <div className="wl-item-main">
        <p className="wl-item-name">{item.product_name || "Unknown Product"}</p>
        <div className="wl-item-meta">
          {item.price     && <span className="wl-item-price">${parseFloat(item.price).toFixed(2)}</span>}
          {item.rating    && <span className="wl-item-rating">★ {parseFloat(item.rating).toFixed(1)}</span>}
          {item.source    && <span className="wl-item-source">{item.source}</span>}
          {item.country   && <span className="wl-item-muted">{item.country === "IN" ? "🇮🇳" : item.country === "GB" ? "🇬🇧" : "🇺🇸"}</span>}
          {item.advanced_value_score &&
            <span className="wl-item-muted">Score: {parseFloat(item.advanced_value_score).toFixed(3)}</span>}
        </div>
        {tab === "wishlist" && item.target_price && (
          <p className={`wl-target ${item.target_reached ? "wl-target-hit" : ""}`}>
            {item.target_reached ? "✅ Target reached!" : `🎯 Target: $${parseFloat(item.target_price).toFixed(2)}`}
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
