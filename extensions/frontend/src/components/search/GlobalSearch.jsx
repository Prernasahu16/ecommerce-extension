/* ============================================================
   EXTENSION — components/search/GlobalSearch.jsx
   Standalone search component — NEW UI only
   Does NOT modify existing ProductList, Nav, or any existing component
   ============================================================ */

import { useState, useEffect, useRef, useCallback } from "react";
import "./GlobalSearch.css";

const COUNTRIES = [
  { code: "",   label: "🌐 All Countries" },
  { code: "US", label: "🇺🇸 United States" },
  { code: "IN", label: "🇮🇳 India" },
  { code: "UK", label: "🇬🇧 United Kingdom" },
];

const SORT_OPTIONS = [
  { value: "advanced_value_score", label: "Best Value" },
  { value: "price",                label: "Price" },
  { value: "rating",               label: "Rating" },
  { value: "discount",             label: "Discount" },
];

export default function GlobalSearch({ onResultsChange, embedded = false }) {
  const [query,    setQuery]    = useState("");
  const [country,  setCountry]  = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [minRating,setMinRating]= useState("");
  const [sort,     setSort]     = useState("advanced_value_score");
  const [loading,  setLoading]  = useState(false);
  const [results,  setResults]  = useState(null);
  const [error,    setError]    = useState(null);
  const debounceRef = useRef(null);

  const BASE = (import.meta.env.VITE_API_URL || "http://localhost:5000") + "/api/ext";

  const doSearch = async (q, opts = {}) => {
    if (!q.trim()) { setResults(null); onResultsChange?.(null); return; }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ q, sort, order: "desc" });
      if (opts.country  || country)  params.set("country",   opts.country  ?? country);
      if (opts.minPrice || minPrice) params.set("min_price", opts.minPrice ?? minPrice);
      if (opts.maxPrice || maxPrice) params.set("max_price", opts.maxPrice ?? maxPrice);
      if (opts.minRating|| minRating)params.set("min_rating",opts.minRating?? minRating);
      const res  = await fetch(`${BASE}/search?${params}`);
      const json = await res.json();
      if (json.success) {
        setResults(json);
        onResultsChange?.(json);
      } else {
        setError(json.error || "Search failed");
      }
    } catch (e) {
      setError("Cannot reach extension API. Make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  };

  // Debounced search on query change
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(query), 400);
    return () => clearTimeout(debounceRef.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, country, minPrice, maxPrice, minRating, sort]);

  const clearAll = () => {
    setQuery(""); setCountry(""); setMinPrice("");
    setMaxPrice(""); setMinRating(""); setResults(null);
    onResultsChange?.(null);
  };

  return (
    <div className={`gs-root ${embedded ? "gs-embedded" : ""}`}>
      {/* Header */}
      {!embedded && (
        <div className="gs-header">
          <span className="gs-badge">NEW</span>
          <h2 className="gs-title">Global Product Search</h2>
          <p className="gs-subtitle">Search across Amazon, Flipkart & more — compare instantly</p>
        </div>
      )}

      {/* Search bar row */}
      <div className="gs-bar">
        <div className="gs-input-wrap">
          <span className="gs-icon">🔍</span>
          <input
            className="gs-input"
            placeholder="Search products across all sources…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && doSearch(query)}
          />
          {query && (
            <button className="gs-clear-btn" onClick={clearAll} title="Clear">✕</button>
          )}
        </div>

        {/* Country selector */}
        <select
          className="gs-select"
          value={country}
          onChange={e => setCountry(e.target.value)}
        >
          {COUNTRIES.map(c => (
            <option key={c.code} value={c.code}>{c.label}</option>
          ))}
        </select>
      </div>

      {/* Filter row */}
      <div className="gs-filters">
        <input
          className="gs-filter-input"
          type="number"
          placeholder="Min price ($)"
          value={minPrice}
          onChange={e => setMinPrice(e.target.value)}
        />
        <input
          className="gs-filter-input"
          type="number"
          placeholder="Max price ($)"
          value={maxPrice}
          onChange={e => setMaxPrice(e.target.value)}
        />
        <input
          className="gs-filter-input"
          type="number"
          min="1" max="5" step="0.5"
          placeholder="Min rating (1-5)"
          value={minRating}
          onChange={e => setMinRating(e.target.value)}
        />
        <select
          className="gs-select gs-select-sm"
          value={sort}
          onChange={e => setSort(e.target.value)}
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* Status bar */}
      {loading && (
        <div className="gs-status">
          <span className="gs-spinner" /> Searching across all sources…
        </div>
      )}
      {error && <div className="gs-error">{error}</div>}
      {results && !loading && (
        <div className="gs-meta">
          Found <strong>{results.total}</strong> products
          {query && <> for "<em>{query}</em>"</>}
          {country && <> in <strong>{COUNTRIES.find(c => c.code === country)?.label}</strong></>}
        </div>
      )}

      {/* Results grid */}
      {results?.data?.length > 0 && (
        <div className="gs-grid">
          {results.data.map(p => (
            <SearchResultCard key={p.std_id} product={p} />
          ))}
        </div>
      )}

      {results?.data?.length === 0 && !loading && (
        <div className="gs-empty">
          <div className="gs-empty-icon">🔎</div>
          <p>No products found. Try ingesting data via the Platform Connector tab.</p>
        </div>
      )}
    </div>
  );
}

// -------------------------------------------------------
// Search Result Card — with Save & Wishlist actions
// -------------------------------------------------------
function SearchResultCard({ product: p }) {
  const [saved,      setSaved]      = useState(false);
  const [wishlisted, setWishlisted] = useState(false);
  const [actionMsg,  setActionMsg]  = useState("");

  const BASE_EXT = (import.meta.env.VITE_API_URL || "http://localhost:5000") + "/api/ext";

  function getSessionId() {
    let id = localStorage.getItem("ext_session_id");
    if (!id) {
      id = "sess_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem("ext_session_id", id);
    }
    return id;
  }

  const showMsg = (msg) => {
    setActionMsg(msg);
    setTimeout(() => setActionMsg(""), 2000);
  };

  const handleSave = async (e) => {
    e.stopPropagation();
    try {
      const res = await fetch(`${BASE_EXT}/saved/${getSessionId()}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ext_product_id: p.ext_product_id }),
      }).then(r => r.json());
      if (res.success) { setSaved(true); showMsg("Saved!"); }
    } catch { showMsg("Error saving"); }
  };

  const handleWishlist = async (e) => {
    e.stopPropagation();
    try {
      const res = await fetch(`${BASE_EXT}/wishlist/${getSessionId()}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ext_product_id: p.ext_product_id }),
      }).then(r => r.json());
      if (res.success) { setWishlisted(true); showMsg("Added to wishlist!"); }
    } catch { showMsg("Error"); }
  };

  const avs = p.advanced_value_score;
  const avsColor =
    avs >= 0.7 ? "var(--gs-positive)" :
    avs >= 0.45 ? "var(--gs-neutral)" : "var(--gs-negative)";

  const sourceColors = {
    amazon:   "#ff9900", amazon_in: "#ff9900", amazon_us: "#ff9900", amazon_uk: "#ff9900",
    flipkart: "#2874f0", fakestore: "var(--gs-accent)", manual: "var(--gs-muted)",
  };
  const srcColor = sourceColors[p.source?.toLowerCase()] || "var(--gs-accent)";

  return (
    <div className="gs-card">
      <div className="gs-card-top">
        <span className="gs-source-badge" style={{ borderColor: srcColor, color: srcColor }}>
          {p.source}
        </span>
        {p.country && (
          <span className="gs-country-tag">
            {p.country === "IN" ? "🇮🇳" : p.country === "GB" ? "🇬🇧" : "🇺🇸"} {p.country}
          </span>
        )}
      </div>

      <p className="gs-card-name">{p.product_name}</p>

      <div className="gs-card-pricing">
        <span className="gs-card-price">${parseFloat(p.price || 0).toFixed(2)}</span>
        {p.original_price && parseFloat(p.original_price) > parseFloat(p.price) && (
          <span className="gs-card-original">${parseFloat(p.original_price).toFixed(2)}</span>
        )}
        {p.discount > 0 && (
          <span className="gs-card-disc">{parseFloat(p.discount).toFixed(0)}% off</span>
        )}
      </div>

      <div className="gs-card-meta">
        {p.rating && <span className="gs-meta-item">★ {parseFloat(p.rating).toFixed(1)}</span>}
        {p.reviews > 0 && (
          <span className="gs-meta-item gs-meta-muted">({p.reviews.toLocaleString()} reviews)</span>
        )}
      </div>

      {avs != null && (
        <div className="gs-avs-row">
          <span className="gs-avs-label">Score</span>
          <div className="gs-avs-bar">
            <div className="gs-avs-fill" style={{ width: `${avs * 100}%`, background: avsColor }} />
          </div>
          <span className="gs-avs-val" style={{ color: avsColor }}>{avs.toFixed(4)}</span>
        </div>
      )}

      {/* Action buttons */}
      <div className="gs-card-actions">
        <button
          className={`gs-action-btn ${wishlisted ? "gs-action-active" : ""}`}
          onClick={handleWishlist}
          title="Add to Wishlist"
        >
          {wishlisted ? "❤️" : "🤍"} Wishlist
        </button>
        <button
          className={`gs-action-btn ${saved ? "gs-action-active" : ""}`}
          onClick={handleSave}
          title="Save product"
        >
          {saved ? "🔖" : "📌"} Save
        </button>
      </div>
      {actionMsg && <div className="gs-action-msg">{actionMsg}</div>}
    </div>
  );
}
