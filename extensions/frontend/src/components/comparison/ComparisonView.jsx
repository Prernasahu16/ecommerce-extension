import { useState } from "react";
import "./ComparisonView.css";

const BASE = (import.meta.env.VITE_API_URL || "http://localhost:5000") + "/api/ext";

export default function ComparisonView() {
  const [query,   setQuery]   = useState("");
  const [loading, setLoading] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState(null);

  const runCompare = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res  = await fetch(`${BASE}/compare?q=${encodeURIComponent(query)}`);
      const json = await res.json();
      if (json.success) {
        const data = json.data;
        const sources = [...new Set((data.results || []).map(p => p.source))];
        const groups = sources.reduce((acc, src) => {
          acc[src] = (data.results || []).filter(p => p.source === src);
          return acc;
        }, {});
        setResult({ ...data, groups, sources });
      } else {
        setError(json.error || "Comparison failed");
      }
    } catch {
      setError("Cannot reach extension API. Make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  };

  const sources = result?.sources || [];

  return (
    <div className="cv-root">
      <div className="cv-header">
        <span className="cv-badge">NEW</span>
        <h2 className="cv-title">Product Comparison Engine</h2>
        <p className="cv-subtitle">Compare the same product across Amazon, Flipkart & more</p>
      </div>

      <div className="cv-search-row">
        <input
          className="cv-input"
          placeholder="Enter product name to compare (e.g. Samsung TV, laptop…)"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === "Enter" && runCompare()}
        />
        <button className="cv-btn" onClick={runCompare} disabled={loading || !query.trim()}>
          {loading ? "Comparing…" : "Compare →"}
        </button>
      </div>

      {error && <div className="cv-error">{error}</div>}

      {result && (
        <>
          <div className="cv-highlights">
            <h3 className="cv-section-title">🏆 Highlights</h3>
            <div className="cv-hl-grid">
              <HighlightCard emoji="💸" label="Lowest Price" value={`$${result.lowest_price?.toFixed(2)}`} color="var(--cv-positive)" />
              <HighlightCard emoji="⭐" label="Best Rating" value={`★ ${result.best_rating?.toFixed(1)}`} color="var(--cv-neutral)" />
              <HighlightCard emoji="📦" label="Total Results" value={result.count} color="var(--cv-accent)" />
            </div>
          </div>

          {sources.length > 0 ? (
            <div className="cv-sources">
              <h3 className="cv-section-title">Results by Source</h3>
              {sources.map(src => (
                <SourceGroup key={src} source={src} products={result.groups[src]} />
              ))}
            </div>
          ) : (
            <div className="cv-empty">
              <div className="cv-empty-icon">🔍</div>
              <p>No products found for "<strong>{query}</strong>".</p>
              <p>Try ingesting data via the Platform Connector first.</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function HighlightCard({ emoji, label, value, color }) {
  return (
    <div className="cv-hl-card" style={{ borderColor: color }}>
      <div className="cv-hl-emoji">{emoji}</div>
      <div className="cv-hl-label">{label}</div>
      <div className="cv-hl-value" style={{ color }}>{value}</div>
    </div>
  );
}

function SourceGroup({ source, products }) {
  const srcColors = {
    amazon: "#ff9900",
    flipkart: "#2874f0",
    fakestore: "var(--cv-accent)",
  };
  const srcColor = srcColors[source?.toLowerCase()] || "var(--cv-accent)";

  return (
    <div className="cv-source-group">
      <div className="cv-source-label" style={{ borderColor: srcColor, color: srcColor }}>
        {source.toUpperCase()}
      </div>
      <div className="cv-product-grid">
        {products.map((p, i) => (
          <div key={i} className="cv-product-card">
            <p className="cv-product-name">
              {p.product_name?.length > 60 ? p.product_name.slice(0, 60) + "…" : p.product_name}
            </p>
            <div className="cv-product-price">
              <span className="cv-price">${parseFloat(p.price || 0).toFixed(2)}</span>
              {p.original_price && parseFloat(p.original_price) > parseFloat(p.price) && (
                <span className="cv-orig">${parseFloat(p.original_price).toFixed(2)}</span>
              )}
              {p.discount > 0 && (
                <span className="cv-disc">{parseFloat(p.discount).toFixed(0)}% off</span>
              )}
            </div>
            <div className="cv-product-meta">
              {p.rating && <span>★ {parseFloat(p.rating).toFixed(1)}</span>}
              {p.reviews > 0 && <span className="cv-meta-muted">· {p.reviews} reviews</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}