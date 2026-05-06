/* ============================================================
   EXTENSION — pages/ExtensionHub.jsx
   Single page that houses ALL new extension features:
     - Global Search
     - Comparison Engine
     - Platform Connector (data ingestion)
     - Wishlist / Saved
     - Extension Stats
   Does NOT modify any existing page component
   ============================================================ */

import { useState } from "react";
import GlobalSearch   from "../components/search/GlobalSearch";
import ComparisonView from "../components/comparison/ComparisonView";
import WishlistPanel  from "../components/wishlist/WishlistPanelPaged";
import "./ExtensionHub.css";

const TABS = [
  { id: "search",     label: "🔍 Global Search"  },
  { id: "compare",    label: "⚖️ Compare"          },
  { id: "ingest",     label: "🔌 Connect Sources"  },
  { id: "wishlist",   label: "❤️ My Lists"         },
  { id: "ext-stats",  label: "📊 Ext Stats"        },
];

export default function ExtensionHub({ externalTab, onTabChange } = {}) {
  const [tab, setTab] = useState("search");

  // Allow shell to drive tab externally (e.g. price-drop badge → wishlist)
  if (externalTab && externalTab !== tab) {
    setTab(externalTab);
    onTabChange?.();
  }

  return (
    <div className="eh-root page">
      <div className="eh-hero">
        <div>
          <div className="eh-badge-row">
            <span className="eh-badge eh-badge-new">NEW MODULE</span>
            <span className="eh-badge eh-badge-ext">Extension Layer</span>
          </div>
          <h1 className="eh-title">Global Intelligence Hub</h1>
          <p className="eh-desc">
            Search, compare &amp; track products across Amazon, Flipkart and more —
            built as a clean extension on top of the existing platform.
          </p>
        </div>
      </div>

      {/* Tab nav */}
      <div className="eh-tabs">
        {TABS.map(t => (
          <button
            key={t.id}
            className={`eh-tab ${tab === t.id ? "eh-tab-active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      <div className="eh-panel">
        {tab === "search"    && <GlobalSearch />}
        {tab === "compare"   && <ComparisonView />}
        {tab === "ingest"    && <ConnectorPanel />}
        {tab === "wishlist"  && <WishlistPanel />}
        {tab === "ext-stats" && <ExtStatsPanel />}
      </div>
    </div>
  );
}

// -------------------------------------------------------
// Platform Connector Panel
// -------------------------------------------------------
function ConnectorPanel() {
  const [platform, setPlatform] = useState("fakestore");
  const [query,    setQuery]    = useState("");
  const [country,  setCountry]  = useState("US");
  const [limit,    setLimit]    = useState(20);
  const [running,  setRunning]  = useState(false);
  const [result,   setResult]   = useState(null);
  const [error,    setError]    = useState(null);

  const BASE = (import.meta.env.VITE_API_URL || "http://localhost:5000") + "/api/ext";

  const PLATFORMS = [
    { value: "fakestore", label: "🛒 FakeStore (Free Demo)" },
    { value: "amazon",    label: "🇺🇸 Amazon (Mock/Real)" },
    { value: "flipkart",  label: "🇮🇳 Flipkart (Mock/Real)" },
  ];

  const run = async () => {
    if (!query.trim()) return;
    setRunning(true); setError(null); setResult(null);
    try {
      const res  = await fetch(`${BASE}/ingest`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ platform, query, limit, country }),
      });
      const json = await res.json();
      if (json.success) setResult(json.data);
      else setError(json.error);
    } catch {
      setError("Cannot reach extension API.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="cp-root">
      <div className="cp-header">
        <span className="cp-badge">NEW</span>
        <h2 className="cp-title">Platform Connector</h2>
        <p className="cp-subtitle">
          Fetch product data from external platforms → standardize → store in extension DB.
          Original data tables remain untouched.
        </p>
      </div>

      <div className="cp-form">
        <div className="cp-field">
          <label className="cp-label">Platform</label>
          <select className="cp-select" value={platform} onChange={e => setPlatform(e.target.value)}>
            {PLATFORMS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>
        <div className="cp-field cp-field-grow">
          <label className="cp-label">Search Query</label>
          <input
            className="cp-input"
            placeholder="e.g. iPhone 14, Samsung Galaxy, laptop…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && run()}
          />
        </div>
        <div className="cp-field">
          <label className="cp-label">Country</label>
          <select className="cp-select" value={country} onChange={e => setCountry(e.target.value)}>
            <option value="US">🇺🇸 US</option>
            <option value="IN">🇮🇳 India</option>
            <option value="GB">🇬🇧 UK</option>
          </select>
        </div>
        <div className="cp-field">
          <label className="cp-label">Limit</label>
          <select className="cp-select" value={limit} onChange={e => setLimit(Number(e.target.value))}>
            {[10, 20, 30, 50].map(n => <option key={n} value={n}>{n} products</option>)}
          </select>
        </div>
        <button className="cp-btn" onClick={run} disabled={running || !query.trim()}>
          {running ? "Fetching…" : "Fetch & Ingest"}
        </button>
      </div>

      {error && <div className="cp-error">{error}</div>}

      {result && (
        <div className="cp-result">
          <div className="cp-result-title">✅ Ingestion Complete</div>
          <div className="cp-result-grid">
            <Stat label="Raw Records"   value={result.total_raw}    />
            <Stat label="Standardized"  value={result.standardized} />
            <Stat label="After Dedup"   value={result.deduped}      />
            <Stat label="Inserted"      value={result.inserted}     color="var(--cv-positive)" />
            <Stat label="Updated"       value={result.updated}      color="var(--cv-neutral)"  />
            <Stat label="Skipped"       value={result.skipped_raw}  color="var(--cv-muted)"    />
          </div>
          <p className="cp-result-note">
            Data stored in <code>standardized_products</code> table.
            Now use <strong>Global Search</strong> or <strong>Compare</strong> to find these products.
          </p>
        </div>
      )}

      <div className="cp-info">
        <h3 className="cp-info-title">How this works</h3>
        <ol className="cp-steps">
          <li>Connector fetches raw data from the selected platform</li>
          <li>Data pipeline standardizes fields &amp; converts currency to USD</li>
          <li>Duplicates removed using source + product ID</li>
          <li><code>advanced_value_score</code> computed for all records</li>
          <li>Stored in <code>standardized_products</code> — original tables unchanged</li>
        </ol>
        <div className="cp-note">
          <strong>Note:</strong> Real Amazon/Flipkart data requires API keys in your <code>.env</code>
          file (<code>RAPIDAPI_KEY</code>, <code>SCRAPERAPI_KEY</code>). Demo data is returned without keys.
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div className="cp-stat">
      <div className="cp-stat-val" style={{ color: color || "var(--cv-text)" }}>{value ?? "—"}</div>
      <div className="cp-stat-label">{label}</div>
    </div>
  );
}

// -------------------------------------------------------
// Extension Stats Panel
// -------------------------------------------------------
function ExtStatsPanel() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const BASE = (import.meta.env.VITE_API_URL || "http://localhost:5000") + "/api/ext";

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const res  = await fetch(`${BASE}/stats`);
      const json = await res.json();
      if (json.success) setData(json.data);
      else setError(json.error);
    } catch {
      setError("Cannot reach extension API.");
    } finally {
      setLoading(false);
    }
  };

  if (!data && !loading && !error) {
    return (
      <div className="es-root">
        <div className="es-header">
          <span className="es-badge">NEW</span>
          <h2 className="es-title">Extension Statistics</h2>
          <p className="es-subtitle">Live stats from the extension data layer (standardized_products)</p>
        </div>
        <button className="es-load-btn" onClick={load}>Load Stats</button>
      </div>
    );
  }

  return (
    <div className="es-root">
      <div className="es-header">
        <span className="es-badge">NEW</span>
        <h2 className="es-title">Extension Statistics</h2>
        <p className="es-subtitle">Live stats from the extension data layer</p>
        <button className="es-refresh-btn" onClick={load} disabled={loading}>↺ Refresh</button>
      </div>

      {loading && <div className="es-loading">Loading stats…</div>}
      {error && <div className="es-error">{error}</div>}

      {data && (
        <>
          <div className="es-overview-grid">
            <StatBox label="Total Products"  value={data.overview?.total_standardized ?? 0} />
            <StatBox label="Sources"         value={data.overview?.total_sources       ?? 0} />
            <StatBox label="Countries"       value={data.overview?.total_countries     ?? 0} />
            <StatBox label="Avg Price (USD)" value={data.overview?.avg_price ? `$${data.overview.avg_price}` : "—"} />
            <StatBox label="Avg Rating"      value={data.overview?.avg_rating ? `★ ${data.overview.avg_rating}` : "—"} />
            <StatBox label="Avg Adv. Score"  value={data.overview?.avg_avs ?? "—"} />
          </div>

          {data.by_source?.length > 0 && (
            <div className="es-by-source">
              <h3 className="es-section-title">Breakdown by Source</h3>
              <table className="es-table">
                <thead>
                  <tr>
                    <th>Source</th><th>Country</th><th>Products</th>
                    <th>Avg Price</th><th>Avg Rating</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_source.map((r, i) => (
                    <tr key={i}>
                      <td><span className="es-source-tag">{r.source}</span></td>
                      <td>{r.country === "IN" ? "🇮🇳" : r.country === "UK" ? "🇬🇧" : "🇺🇸"} {r.country}</td>
                      <td>{r.count}</td>
                      <td>${r.avg_price}</td>
                      <td>★ {r.avg_rating}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatBox({ label, value }) {
  return (
    <div className="es-stat-box">
      <div className="es-stat-val">{value}</div>
      <div className="es-stat-label">{label}</div>
    </div>
  );
}
