# ============================================================
# EXTENSION MODULE — data_pipeline/pipeline.py
# Clean, independent data processing layer
# Standardizes into: product_name, price, original_price,
#   discount, rating, reviews, source, country
# Removes duplicates via (source, source_product_id)
# NEVER touches: products, market_prices, price_history tables
# ============================================================

import logging
import hashlib
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import query, execute, get_connection

log = logging.getLogger(__name__)

SUPPORTED_COUNTRIES = {"IN", "US", "UK"}
CURRENCY_MAP = {"IN": "INR", "US": "USD", "UK": "GBP"}

# USD conversion rates (approximate)
EXCHANGE_RATES = {
    "USD": 1.0,
    "INR": 1 / 84.0,
    "GBP": 1.27,
    "EUR": 1.09,
}


# -------------------------------------------------------
# FIELD STANDARDIZER
# Maps any incoming dict to the canonical schema
# -------------------------------------------------------
def standardize_record(raw: dict, source: str, country: str = "US") -> dict | None:
    """
    Normalize an incoming product dict to the canonical schema.
    Returns None if the record is invalid (no name or price).
    """
    # --- name ---
    name = (
        raw.get("product_name") or
        raw.get("name") or
        raw.get("title") or
        raw.get("productName") or ""
    ).strip()
    if not name:
        return None

    # --- price ---
    def _to_float(v, fallback=None):
        try:
            return float(str(v).replace(",", "").replace("₹", "").replace("$", "").replace("£", "").strip())
        except (TypeError, ValueError):
            return fallback

    price = _to_float(
        raw.get("price") or
        raw.get("market_price") or
        raw.get("salePrice") or
        raw.get("selling_price")
    )
    if price is None or price <= 0:
        return None

    original_price = _to_float(
        raw.get("original_price") or
        raw.get("mrp") or
        raw.get("originalPrice") or
        raw.get("listPrice"),
        fallback=price,
    )
    if original_price < price:
        original_price = price  # guard against bad data

    # --- discount ---
    if original_price > 0:
        discount = round((original_price - price) / original_price * 100, 2)
    else:
        discount = 0.0

    # --- rating ---
    rating = _to_float(raw.get("rating") or raw.get("stars") or raw.get("averageRating"), fallback=3.0)
    rating = max(1.0, min(5.0, rating))

    # --- reviews ---
    reviews = int(_to_float(
        raw.get("reviews") or raw.get("review_count") or
        raw.get("numReviews") or raw.get("reviewCount"), fallback=0
    ) or 0)

    # --- currency → USD normalisation ---
    currency = CURRENCY_MAP.get(country, "USD")
    rate = EXCHANGE_RATES.get(currency, 1.0)
    price_usd = round(price * rate, 2)
    orig_usd = round(original_price * rate, 2)

    # --- source product id (dedup key) ---
    source_product_id = (
        str(raw.get("id") or raw.get("product_id") or
            raw.get("asin") or raw.get("sku") or
            hashlib.md5(f"{source}::{name}::{price}".encode()).hexdigest())
    )

    return {
        "product_name":      name,
        "price":             price_usd,
        "original_price":    orig_usd,
        "discount":          discount,
        "rating":            round(rating, 1),
        "reviews":           reviews,
        "source":            source,
        "country":           country[:2].upper() if country in SUPPORTED_COUNTRIES else "US",
        "currency":          "USD",
        "source_product_id": source_product_id,
    }


# -------------------------------------------------------
# ADVANCED VALUE SCORE (non-destructive — new field only)
# Formula: 0.35*norm_rating + 0.25*norm_reviews_log
#         + 0.25*norm_discount + 0.15*norm_price_inv
# Stored in advanced_value_score ONLY — never replaces value_score
# -------------------------------------------------------
def compute_advanced_value_score(records: list[dict]) -> list[dict]:
    """
    Compute advanced_value_score for a batch of standardized records.
    Adds the field in-place and returns the list.
    """
    import math

    def _norm(values, invert=False):
        if not values:
            return values
        mn, mx = min(values), max(values)
        rng = mx - mn
        if rng == 0:
            return [0.5] * len(values)
        out = [(v - mn) / rng for v in values]
        return [1 - x for x in out] if invert else out

    ratings   = [float(r["rating"])             for r in records]
    prices    = [float(r["price"])               for r in records]
    discounts = [float(r["discount"])            for r in records]
    rev_logs  = [math.log1p(r["reviews"])        for r in records]

    norm_r  = _norm(ratings)
    norm_p  = _norm(prices, invert=True)
    norm_d  = _norm(discounts)
    norm_rv = _norm(rev_logs)

    for i, rec in enumerate(records):
        rec["advanced_value_score"] = round(
            0.35 * norm_r[i] +
            0.25 * norm_rv[i] +
            0.25 * norm_d[i] +
            0.15 * norm_p[i],
            4,
        )
    return records


# -------------------------------------------------------
# UPSERT TO standardized_products
# -------------------------------------------------------
def upsert_standardized(records: list[dict]) -> tuple[int, int]:
    """
    Upsert a list of standardized records into standardized_products.
    Returns (inserted, updated) counts.
    """
    if not records:
        return 0, 0

    conn = get_connection()
    cur  = conn.cursor()
    inserted = updated = 0

    for rec in records:
        try:
            cur.execute("""
                INSERT INTO standardized_products
                    (product_name, price, original_price, discount,
                     rating, reviews, source, country, currency,
                     source_product_id, advanced_value_score)
                VALUES
                    (%(product_name)s, %(price)s, %(original_price)s, %(discount)s,
                     %(rating)s, %(reviews)s, %(source)s, %(country)s, %(currency)s,
                     %(source_product_id)s, %(advanced_value_score)s)
                ON CONFLICT (source, source_product_id) DO UPDATE SET
                    product_name          = EXCLUDED.product_name,
                    price                 = EXCLUDED.price,
                    original_price        = EXCLUDED.original_price,
                    discount              = EXCLUDED.discount,
                    rating                = EXCLUDED.rating,
                    reviews               = EXCLUDED.reviews,
                    advanced_value_score  = EXCLUDED.advanced_value_score,
                    updated_at            = CURRENT_TIMESTAMP
                RETURNING (xmax = 0) AS inserted
            """, rec)
            row = cur.fetchone()
            if row and row[0]:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            log.warning(f"[Pipeline] Upsert skipped: {e}")

    conn.commit()

    # Track price history for any price change
    for rec in records:
        try:
            std = cur.execute(
                "SELECT std_id, price FROM standardized_products "
                "WHERE source=%s AND source_product_id=%s",
                (rec["source"], rec["source_product_id"])
            )
            row = cur.fetchone() if std else None
            if row:
                cur.execute("""
                    INSERT INTO ext_price_history (std_id, price, original_price, currency, source)
                    SELECT %s, %s, %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM ext_price_history
                        WHERE std_id=%s AND price=%s
                          AND recorded_at > NOW() - INTERVAL '1 hour'
                    )
                """, (row[0], rec["price"], rec["original_price"],
                      rec["currency"], rec["source"],
                      row[0], rec["price"]))
        except Exception as e:
            log.debug(f"[Pipeline] Price history skip: {e}")

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"[Pipeline] Upserted: {inserted} inserted, {updated} updated")
    return inserted, updated


# -------------------------------------------------------
# MAIN ENTRY — process a raw batch from any source
# -------------------------------------------------------
def process_batch(raw_records: list[dict], source: str, country: str = "US") -> dict:
    """
    Full pipeline:
      1. Standardize fields
      2. Compute advanced_value_score
      3. Remove duplicates
      4. Upsert to DB
    """
    # Step 1: standardize
    standardized = []
    skipped = 0
    for raw in raw_records:
        std = standardize_record(raw, source, country)
        if std:
            standardized.append(std)
        else:
            skipped += 1

    # Step 2: dedup within batch (keep last occurrence per source_product_id)
    seen = {}
    for rec in standardized:
        seen[rec["source_product_id"]] = rec
    deduped = list(seen.values())

    # Step 3: score
    if deduped:
        compute_advanced_value_score(deduped)

    # Step 4: upsert
    inserted, updated = upsert_standardized(deduped)

    result = {
        "total_raw":    len(raw_records),
        "standardized": len(standardized),
        "deduped":      len(deduped),
        "skipped_raw":  skipped,
        "inserted":     inserted,
        "updated":      updated,
    }
    log.info(f"[Pipeline] Batch result: {result}")
    return result
