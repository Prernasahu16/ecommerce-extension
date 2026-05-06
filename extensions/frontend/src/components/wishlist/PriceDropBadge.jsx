/* ============================================================
   EXTENSION — components/wishlist/PriceDropBadge.jsx
   Shows a notification badge when wishlist items hit target price.
   Rendered next to the wishlist tab in ExtensionHub.
   Polls /api/ext/alerts/<session_id> every 5 minutes.
   ============================================================ */

import { useState, useEffect } from "react";
import "./PriceDropBadge.css";

const BASE = (import.meta.env.VITE_API_URL || "http://localhost:5000") + "/api/ext";
const POLL_MS = 5 * 60 * 1000; // 5 minutes

function getSessionId() {
  let id = localStorage.getItem("ext_session_id");
  if (!id) {
    id = "sess_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("ext_session_id", id);
  }
  return id;
}

export default function PriceDropBadge({ onClick }) {
  const [alerts, setAlerts] = useState([]);
  const [open,   setOpen]   = useState(false);

  const fetchAlerts = async () => {
    try {
      const res  = await fetch(`${BASE}/alerts/${getSessionId()}`);
      const json = await res.json();
      if (json.success) setAlerts(json.data || []);
    } catch { /* silent — badge is non-critical */ }
  };

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, POLL_MS);
    return () => clearInterval(interval);
  }, []);

  if (alerts.length === 0) return null;

  return (
    <div className="pdb-root">
      <button
        className="pdb-trigger"
        onClick={() => setOpen(o => !o)}
        title={`${alerts.length} price drop${alerts.length > 1 ? "s" : ""}!`}
      >
        🔔
        <span className="pdb-count">{alerts.length}</span>
      </button>

      {open && (
        <div className="pdb-panel">
          <div className="pdb-header">
            <span>💸 Price Drops</span>
            <button className="pdb-close" onClick={() => setOpen(false)}>✕</button>
          </div>
          <div className="pdb-list">
            {alerts.map(a => (
              <div key={a.wish_id} className="pdb-item" onClick={() => { onClick?.(); setOpen(false); }}>
                <p className="pdb-name">{a.product_name?.slice(0, 50)}{a.product_name?.length > 50 ? "…" : ""}</p>
                <div className="pdb-prices">
                  <span className="pdb-now">${a.current_price.toFixed(2)}</span>
                  <span className="pdb-was">target ${a.target_price.toFixed(2)}</span>
                  <span className="pdb-save">−${a.savings.toFixed(2)}</span>
                </div>
                <span className="pdb-src">{a.source}</span>
              </div>
            ))}
          </div>
          <p className="pdb-footer">Click any item to view your wishlist</p>
        </div>
      )}
    </div>
  );
}
