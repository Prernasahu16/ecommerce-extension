# ============================================================
# EXTENSION LAYER — Product Comparison Engine
# FILE: backend/services/comparison_engine.py
# PURPOSE: Finds similar products across different sources,
#          groups them, and identifies lowest price & best rating.
#          Reads only from ext_processed_products. Zero impact
#          on existing products / value_scores tables.
# ============================================================

import logging
import re
from difflib import SequenceMatcher
from db import get_connection, query

log = logging.getLogger(__name__)

# Similarity threshold (0–1) for name matching
SIMILARITY_THRESHOLD = float(0.45)


# -------------------------------------------------------
# TEXT NORMALISER
# -------------------------------------------------------
def _normalise_name(name: str) -> str:
    """Lower, strip punctuation/numbers for fuzzy matching."""
    name = name.lower()
    name = re.sub(r"[^a-z\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalise_name(a), _normalise_name(b)).ratio()


# -------------------------------------------------------
# KEYWORD EXTRACTOR — pull 2–3 word noun phrase from name
# -------------------------------------------------------
def _extract_keyword(name: str) -> str:
    words = _normalise_name(name).split()
    # Drop common generic words
    stopwords = {"the", "a", "an", "and", "with", "for", "in", "of",
                 "new", "best", "top", "premium", "pro", "plus", "ultra"}
    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    return " ".join(keywords[:3])


# -------------------------------------------------------
# COMPARE: find similar products for a given ext_product_id
# -------------------------------------------------------
def compare_product(ext_product_id: str, max_results: int = 10) -> dict:
    """
    Given one ext_product_id, return similar products from OTHER sources,
    ranked by advanced_value_score, with lowest_price and best_rating flagged.
    """
    anchor = query(
        "SELECT * FROM ext_processed_products WHERE ext_product_id = %s",
        (ext_product_id,), fetch="one"
    )
    if not anchor:
        return {"error": "Product not found", "results": []}

    keyword = _extract_keyword(anchor["product_name"])
    category = anchor.get("category", "")

    # Fetch candidates from OTHER sources in same broad category
    candidates = query("""
        SELECT ep.*, eas.advanced_value_score
        FROM ext_processed_products ep
        LEFT JOIN ext_advanced_scores eas ON eas.ext_product_id = ep.ext_product_id
        WHERE ep.ext_product_id != %s
          AND ep.source != %s
        ORDER BY ep.updated_at DESC
        LIMIT 500
    """, (ext_product_id, anchor["source"]))

    # Score similarity
    scored = []
    for c in candidates:
        sim = _similarity(anchor["product_name"], c["product_name"])
        if sim >= SIMILARITY_THRESHOLD:
            scored.append({**c, "_similarity": round(sim, 3)})

    # Sort by similarity desc, take top results
    scored.sort(key=lambda x: x["_similarity"], reverse=True)
    results = scored[:max_results]

    if not results:
        return {
            "anchor":  _format_product(anchor),
            "keyword": keyword,
            "results": [],
            "message": "No similar products found across sources"
        }

    # Flag lowest price and best rating
    min_price  = min(float(r["price"] or 9999) for r in results)
    max_rating = max(float(r["rating"] or 0)   for r in results)

    formatted = []
    for r in results:
        fp = _format_product(r)
        fp["is_lowest_price"] = float(r["price"] or 0) == min_price
        fp["is_best_rating"]  = float(r["rating"] or 0) == max_rating
        fp["similarity_score"] = r["_similarity"]
        formatted.append(fp)

    return {
        "anchor":        _format_product(anchor),
        "keyword":       keyword,
        "results":       formatted,
        "lowest_price":  min_price,
        "best_rating":   max_rating,
    }


# -------------------------------------------------------
# COMPARE: search-based comparison by keyword
# -------------------------------------------------------
def compare_by_keyword(keyword: str, country: str = None,
                       max_results: int = 20) -> dict:
    """
    Search for products matching keyword across all sources,
    return grouped comparison with highlights.
    """
    params  = [f"%{keyword.lower()}%"]
    country_filter = ""
    if country:
        country_filter = "AND UPPER(ep.country) = UPPER(%s)"
        params.append(country)

    rows = query(f"""
        SELECT ep.*, eas.advanced_value_score
        FROM ext_processed_products ep
        LEFT JOIN ext_advanced_scores eas ON eas.ext_product_id = ep.ext_product_id
        WHERE LOWER(ep.product_name) LIKE %s
        {country_filter}
        ORDER BY eas.advanced_value_score DESC NULLS LAST
        LIMIT %s
    """, params + [max_results])

    if not rows:
        return {"keyword": keyword, "results": [], "message": "No products found"}

    min_price  = min(float(r["price"] or 9999) for r in rows)
    max_rating = max(float(r["rating"] or 0)   for r in rows)

    results = []
    for r in rows:
        fp = _format_product(r)
        fp["is_lowest_price"] = float(r["price"] or 0) == min_price
        fp["is_best_rating"]  = float(r["rating"] or 0) == max_rating
        results.append(fp)

    return {
        "keyword":      keyword,
        "country":      country,
        "results":      results,
        "lowest_price": min_price,
        "best_rating":  max_rating,
        "count":        len(results),
    }


# -------------------------------------------------------
# HELPER
# -------------------------------------------------------
def _format_product(r: dict) -> dict:
    return {
        "ext_product_id":       str(r.get("ext_product_id", "")),
        "product_name":         r.get("product_name", ""),
        "price":                float(r.get("price") or 0),
        "original_price":       float(r.get("original_price") or 0),
        "discount":             float(r.get("discount") or 0),
        "rating":               float(r.get("rating") or 0),
        "reviews":              int(r.get("reviews") or 0),
        "source":               r.get("source", ""),
        "country":              r.get("country", ""),
        "category":             r.get("category", ""),
        "image_url":            r.get("image_url", ""),
        "product_url":          r.get("product_url", ""),
        "advanced_value_score": float(r.get("advanced_value_score") or 0),
    }
