# ============================================================
# EXTENSION LAYER — Clean Data Processing Pipeline
# FILE: backend/services/data_pipeline.py
# PURPOSE: Ingest raw product data from any source, standardize
#          it into a canonical schema, deduplicate, and persist
#          into ext_processed_products WITHOUT touching existing tables.
# ============================================================

import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any
from db import get_connection, query

log = logging.getLogger(__name__)

# -------------------------------------------------------
# CANONICAL SCHEMA DEFINITION
# Every product in the extension layer must conform to this.
# -------------------------------------------------------
CANONICAL_FIELDS = [
    "product_name",   # str   — required
    "price",          # float — required
    "original_price", # float — optional, defaults to price
    "discount",       # float — computed or provided
    "rating",         # float 1–5
    "reviews",        # int   — review count
    "source",         # str   — origin platform
    "country",        # str   — 2-char ISO  (US | IN | GB)
    "category",       # str
    "image_url",      # str
    "product_url",    # str
    "raw_external_id" # str   — original ID in source system
]


# -------------------------------------------------------
# FIELD STANDARDIZER
# Accepts raw dicts from any connector and normalises them.
# -------------------------------------------------------
def standardize(raw: dict, source: str, country: str = "US") -> dict | None:
    """
    Coerce a raw product dict into canonical form.
    Returns None if required fields are missing / invalid.
    """
    try:
        name = str(raw.get("product_name") or raw.get("name") or raw.get("title") or "").strip()
        if not name:
            return None

        # Price coercion — handle string "$12.99", float, int
        def _to_float(v, default=0.0):
            if v is None:
                return default
            try:
                return float(str(v).replace("$", "").replace("₹", "").replace("£", "").replace(",", "").strip())
            except (ValueError, TypeError):
                return default

        price          = _to_float(raw.get("price") or raw.get("market_price"))
        original_price = _to_float(raw.get("original_price") or raw.get("mrp") or raw.get("was_price"), price)

        if price <= 0:
            return None

        # Discount
        if original_price > price:
            discount = round((original_price - price) / original_price * 100, 2)
        else:
            discount = _to_float(raw.get("discount") or raw.get("discount_pct"), 0.0)

        rating  = min(5.0, max(0.0, _to_float(raw.get("rating") or raw.get("stars"), 0.0)))
        reviews = int(_to_float(raw.get("reviews") or raw.get("review_count") or raw.get("num_reviews"), 0))

        return {
            "product_name":    name,
            "price":           round(price, 2),
            "original_price":  round(original_price, 2),
            "discount":        discount,
            "rating":          round(rating, 1),
            "reviews":         reviews,
            "source":          source,
            "country":         country.upper()[:2],
            "category":        str(raw.get("category") or raw.get("type") or "General").strip(),
            "image_url":       str(raw.get("image_url") or raw.get("image") or ""),
            "product_url":     str(raw.get("product_url") or raw.get("url") or ""),
            "raw_external_id": str(raw.get("id") or raw.get("external_id") or raw.get("asin") or ""),
        }
    except Exception as e:
        log.warning(f"[Pipeline] Standardize error: {e} | raw={raw}")
        return None


# -------------------------------------------------------
# DEDUPLICATION KEY
# Unique fingerprint to prevent duplicates across ingestions.
# -------------------------------------------------------
def _source_key(product: dict) -> str:
    """
    Builds a dedup key: source:country:external_id OR name-price hash.
    """
    ext_id = product.get("raw_external_id", "").strip()
    source  = product.get("source", "").lower()
    country = product.get("country", "US").upper()

    if ext_id:
        return f"{source}:{country}:{ext_id}"

    # Fallback: hash on name + price
    fingerprint = f"{source}:{country}:{product['product_name'].lower()}:{product['price']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()


# -------------------------------------------------------
# PERSIST TO ext_processed_products
# -------------------------------------------------------
def _upsert_product(conn, product: dict, source_key: str) -> str | None:
    """
    Insert or update a product in ext_processed_products.
    Returns the ext_product_id.
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO ext_processed_products
                (source_key, product_name, price, original_price, discount,
                 rating, reviews, source, country, category,
                 image_url, product_url, raw_external_id, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CURRENT_TIMESTAMP)
            ON CONFLICT (source_key) DO UPDATE SET
                product_name   = EXCLUDED.product_name,
                price          = EXCLUDED.price,
                original_price = EXCLUDED.original_price,
                discount       = EXCLUDED.discount,
                rating         = EXCLUDED.rating,
                reviews        = EXCLUDED.reviews,
                category       = EXCLUDED.category,
                image_url      = EXCLUDED.image_url,
                product_url    = EXCLUDED.product_url,
                updated_at     = CURRENT_TIMESTAMP
            RETURNING ext_product_id
        """, (
            source_key,
            product["product_name"], product["price"], product["original_price"],
            product["discount"], product["rating"], product["reviews"],
            product["source"], product["country"], product["category"],
            product["image_url"], product["product_url"], product["raw_external_id"]
        ))
        row = cur.fetchone()
        return str(row[0]) if row else None
    finally:
        cur.close()


def _record_price_history(conn, ext_product_id: str, product: dict):
    """Append a price snapshot to ext_price_history."""
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO ext_price_history (ext_product_id, price, original_price, source)
            SELECT %s, %s, %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM ext_price_history
                WHERE ext_product_id = %s
                  AND price = %s
                  AND recorded_at > NOW() - INTERVAL '24 hours'
            )
        """, (
            ext_product_id, product["price"], product["original_price"], product["source"],
            ext_product_id, product["price"]
        ))
    finally:
        cur.close()


# -------------------------------------------------------
# PUBLIC ENTRY POINT
# -------------------------------------------------------
def ingest(raw_products: list[dict], source: str, country: str = "US") -> dict:
    """
    Main pipeline entry point.
    1. Standardize each raw product dict
    2. Deduplicate using source_key
    3. Upsert into ext_processed_products
    4. Append price snapshots

    Returns:
        {"total": int, "inserted": int, "updated": int, "skipped": int}
    """
    log.info(f"[Pipeline] Ingesting {len(raw_products)} products from {source}/{country}")
    inserted = updated = skipped = 0

    conn = get_connection()
    cur  = conn.cursor()

    try:
        # Pre-fetch existing keys for this source+country to classify insert vs update
        cur.execute(
            "SELECT source_key FROM ext_processed_products WHERE source=%s AND country=%s",
            (source, country.upper()[:2])
        )
        existing_keys = {row[0] for row in cur.fetchall()}

        for raw in raw_products:
            product = standardize(raw, source, country)
            if product is None:
                skipped += 1
                continue

            sk = _source_key(product)
            is_new = sk not in existing_keys

            ext_id = _upsert_product(conn, product, sk)
            if ext_id:
                _record_price_history(conn, ext_id, product)
                if is_new:
                    inserted += 1
                else:
                    updated += 1
            else:
                skipped += 1

        conn.commit()
        log.info(f"[Pipeline] Done — inserted={inserted}, updated={updated}, skipped={skipped}")
        return {
            "total":    len(raw_products),
            "inserted": inserted,
            "updated":  updated,
            "skipped":  skipped
        }

    except Exception as e:
        conn.rollback()
        log.error(f"[Pipeline] Ingest error: {e}")
        raise
    finally:
        cur.close()
        conn.close()
