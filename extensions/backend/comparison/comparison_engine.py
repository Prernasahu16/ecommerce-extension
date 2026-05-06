# ============================================================
# EXTENSION MODULE — comparison/comparison_engine.py
# Matches similar products across sources and ranks them
# Outputs: lowest price, best rating, advanced_value_score
# DOES NOT modify existing products or value_scores tables
# ============================================================

import logging
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import query

log = logging.getLogger(__name__)


# -------------------------------------------------------
# SIMILARITY HELPERS
# -------------------------------------------------------
def _tokenize(name: str) -> set[str]:
    """Lowercase, strip punctuation, return word tokens."""
    name = re.sub(r"[^\w\s]", " ", name.lower())
    return set(name.split())


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity_score(name_a: str, name_b: str) -> float:
    """Jaccard similarity between two product names."""
    return _jaccard(_tokenize(name_a), _tokenize(name_b))


# -------------------------------------------------------
# MATCH SIMILAR PRODUCTS
# -------------------------------------------------------
def find_similar_products(product_name: str, threshold: float = 0.3,
                          limit: int = 20) -> list[dict]:
    """
    Find standardized_products that are similar to a given product name.
    Uses trigram index in Postgres for fast candidate retrieval,
    then refines with Jaccard similarity.
    """
    rows = query("""
        SELECT std_id, product_name, price, original_price, discount,
               rating, reviews, source, country, advanced_value_score
        FROM standardized_products
        WHERE product_name ILIKE %s
           OR similarity(product_name, %s) > 0.15
        ORDER BY similarity(product_name, %s) DESC
        LIMIT %s
    """, (f"%{product_name.split()[0]}%", product_name, product_name, limit * 5))

    # Re-rank with Jaccard
    scored = []
    for r in rows:
        sim = similarity_score(product_name, r["product_name"])
        if sim >= threshold:
            scored.append({**r, "_similarity": round(sim, 3)})

    scored.sort(key=lambda x: x["_similarity"], reverse=True)
    return scored[:limit]


# -------------------------------------------------------
# COMPARE PRODUCTS BY NAME
# -------------------------------------------------------
def compare_products(search_query: str, limit_per_source: int = 5) -> dict:
    """
    Find all standardized products matching the search query.
    Group by source, highlight:
      - lowest_price
      - best_rating
      - best_value (highest advanced_value_score)
    """
    rows = query("""
        SELECT std_id, product_name, price, original_price, discount,
               rating, reviews, source, country, advanced_value_score
        FROM standardized_products
        WHERE product_name ILIKE %s
        ORDER BY advanced_value_score DESC NULLS LAST
        LIMIT %s
    """, (f"%{search_query}%", limit_per_source * 10))

    if not rows:
        return {
            "query": search_query,
            "total": 0,
            "groups": {},
            "highlights": {},
        }

    # Group by source
    groups: dict[str, list] = {}
    for r in rows:
        src = r["source"]
        groups.setdefault(src, []).append(r)

    # Limit per source
    for src in groups:
        groups[src] = groups[src][:limit_per_source]

    all_products = [p for g in groups.values() for p in g]

    # Highlights
    valid_prices  = [p for p in all_products if p.get("price") and float(p["price"]) > 0]
    valid_ratings = [p for p in all_products if p.get("rating") and float(p["rating"]) > 0]
    valid_scores  = [p for p in all_products if p.get("advanced_value_score")]

    highlights = {}
    if valid_prices:
        lp = min(valid_prices, key=lambda x: float(x["price"]))
        highlights["lowest_price"] = {
            "std_id":       str(lp["std_id"]),
            "product_name": lp["product_name"],
            "price":        float(lp["price"]),
            "source":       lp["source"],
        }
    if valid_ratings:
        br = max(valid_ratings, key=lambda x: float(x["rating"]))
        highlights["best_rating"] = {
            "std_id":       str(br["std_id"]),
            "product_name": br["product_name"],
            "rating":       float(br["rating"]),
            "source":       br["source"],
        }
    if valid_scores:
        bv = max(valid_scores, key=lambda x: float(x["advanced_value_score"]))
        highlights["best_value"] = {
            "std_id":                str(bv["std_id"]),
            "product_name":          bv["product_name"],
            "advanced_value_score":  float(bv["advanced_value_score"]),
            "source":                bv["source"],
        }

    return {
        "query":      search_query,
        "total":      len(all_products),
        "groups":     {src: _serialize_group(g) for src, g in groups.items()},
        "highlights": highlights,
    }


def _serialize_group(products: list[dict]) -> list[dict]:
    return [
        {
            "std_id":               str(p["std_id"]),
            "product_name":         p["product_name"],
            "price":                float(p["price"]) if p.get("price") else None,
            "original_price":       float(p["original_price"]) if p.get("original_price") else None,
            "discount":             float(p["discount"]) if p.get("discount") else None,
            "rating":               float(p["rating"]) if p.get("rating") else None,
            "reviews":              int(p["reviews"]) if p.get("reviews") else 0,
            "source":               p["source"],
            "country":              p["country"],
            "advanced_value_score": float(p["advanced_value_score"]) if p.get("advanced_value_score") else None,
        }
        for p in products
    ]


# -------------------------------------------------------
# PRICE HISTORY for a standardized product
# -------------------------------------------------------
def get_price_history(std_id: str) -> list[dict]:
    rows = query("""
        SELECT price, original_price, currency, source, recorded_at
        FROM ext_price_history
        WHERE std_id = %s
        ORDER BY recorded_at ASC
        LIMIT 90
    """, (std_id,))
    return [
        {
            "price":          float(r["price"]),
            "original_price": float(r["original_price"]) if r.get("original_price") else None,
            "currency":       r["currency"],
            "source":         r["source"],
            "recorded_at":    r["recorded_at"].isoformat() if r.get("recorded_at") else None,
        }
        for r in rows
    ]
