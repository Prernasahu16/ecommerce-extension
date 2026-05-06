# ============================================================
# EXTENSION LAYER — Advanced Value Score Engine
# FILE: backend/ml/advanced_score.py
# PURPOSE: Computes 'advanced_value_score' for ext_processed_products.
#          NEVER touches value_scores table (existing) or existing
#          value_score field.  Stores in ext_advanced_scores only.
# ============================================================

import logging
import math
from db import get_connection, query

log = logging.getLogger(__name__)


# -------------------------------------------------------
# SCORING FORMULA
# Inputs: price, rating, reviews (log-scaled), discount
# Each factor is normalised 0–1 then weighted.
# Weights are configurable — defaults inspired by research
# on consumer decision-making (price > rating > reviews > discount).
# -------------------------------------------------------
DEFAULT_WEIGHTS = {
    "price":    0.35,   # lower price → higher score (inverted)
    "rating":   0.30,   # higher rating → higher score
    "reviews":  0.20,   # more reviews → more trust (log-scaled)
    "discount": 0.15,   # bigger discount → better deal
}


def _safe_float(v, default=0.0) -> float:
    try:
        return float(v or default)
    except (ValueError, TypeError):
        return default


def _normalize_list(values: list[float], invert: bool = False) -> list[float]:
    """Min-max normalise; invert for lower-is-better metrics."""
    if not values:
        return []
    mn, mx = min(values), max(values)
    rng = mx - mn
    if rng == 0:
        return [0.5] * len(values)
    normed = [(v - mn) / rng for v in values]
    return [1.0 - n for n in normed] if invert else normed


def compute_advanced_scores(weights: dict = None) -> int:
    """
    Compute advanced_value_score for all ext_processed_products.
    Persists results into ext_advanced_scores (upsert by ext_product_id).
    Returns number of products scored.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    # Normalise weights
    total = sum(w.values()) or 1
    w = {k: v / total for k, v in w.items()}

    rows = query("""
        SELECT ep.ext_product_id, ep.price, ep.rating, ep.reviews, ep.discount
        FROM ext_processed_products ep
        WHERE ep.price IS NOT NULL AND ep.price > 0
    """)

    if not rows:
        log.warning("[AdvancedScore] No ext products found")
        return 0

    prices    = [_safe_float(r["price"])    for r in rows]
    ratings   = [_safe_float(r["rating"])   for r in rows]
    reviews   = [math.log1p(_safe_float(r["reviews"])) for r in rows]  # log-scale
    discounts = [_safe_float(r["discount"]) for r in rows]

    norm_prices    = _normalize_list(prices,    invert=True)
    norm_ratings   = _normalize_list(ratings)
    norm_reviews   = _normalize_list(reviews)
    norm_discounts = _normalize_list(discounts)

    conn = get_connection()
    cur  = conn.cursor()
    count = 0

    try:
        for i, r in enumerate(rows):
            pf = norm_prices[i]
            rf = norm_ratings[i]
            vf = norm_reviews[i]
            df = norm_discounts[i]

            adv_score = round(
                w["price"]    * pf +
                w["rating"]   * rf +
                w["reviews"]  * vf +
                w["discount"] * df,
                4
            )

            cur.execute("""
                INSERT INTO ext_advanced_scores
                    (ext_product_id, price_factor, rating_factor,
                     reviews_factor, discount_factor, advanced_value_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ext_product_id) DO UPDATE SET
                    price_factor         = EXCLUDED.price_factor,
                    rating_factor        = EXCLUDED.rating_factor,
                    reviews_factor       = EXCLUDED.reviews_factor,
                    discount_factor      = EXCLUDED.discount_factor,
                    advanced_value_score = EXCLUDED.advanced_value_score,
                    computed_at          = CURRENT_TIMESTAMP
            """, (
                r["ext_product_id"], round(pf,4), round(rf,4),
                round(vf,4), round(df,4), adv_score
            ))
            count += 1

        conn.commit()
        log.info(f"[AdvancedScore] Scored {count} ext products")
        return count

    except Exception as e:
        conn.rollback()
        log.error(f"[AdvancedScore] Error: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def score_single(price: float, rating: float, reviews: int,
                 discount: float, weights: dict = None) -> dict:
    """
    Compute advanced_value_score for a single product inline
    (used by the API to enrich search results without a DB round-trip).
    Returns factor breakdown + final score.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total = sum(w.values()) or 1
    w = {k: v / total for k, v in w.items()}

    # Heuristic normalisation for single-product context
    norm_price    = max(0.0, 1.0 - min(price / 2000.0, 1.0))   # up to $2000 cap
    norm_rating   = (rating - 1.0) / 4.0 if rating > 0 else 0.0
    norm_reviews  = min(math.log1p(reviews) / math.log1p(50000), 1.0)
    norm_discount = min(discount / 80.0, 1.0)

    adv_score = round(
        w["price"]    * norm_price +
        w["rating"]   * norm_rating +
        w["reviews"]  * norm_reviews +
        w["discount"] * norm_discount,
        4
    )

    return {
        "advanced_value_score": adv_score,
        "factors": {
            "price_factor":    round(norm_price, 4),
            "rating_factor":   round(norm_rating, 4),
            "reviews_factor":  round(norm_reviews, 4),
            "discount_factor": round(norm_discount, 4),
        },
        "weights": w,
    }
