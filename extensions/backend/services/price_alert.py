# ============================================================
# EXTENSION — services/price_alert.py
# Checks wishlist items for price drops below target_price.
# Called by scheduler (every 4h) or on-demand via API.
# Reads from ext_wishlist + ext_processed_products only.
# ============================================================

import logging
from db import query, get_connection

log = logging.getLogger(__name__)


def check_all_alerts() -> dict:
    """
    Scan all wishlist rows where target_price is set.
    Returns summary of items that have reached their target.
    """
    rows = query("""
        SELECT w.wish_id, w.session_id, w.ext_product_id, w.target_price,
               ep.product_name, ep.price, ep.source
        FROM ext_wishlist w
        JOIN ext_processed_products ep ON ep.ext_product_id = w.ext_product_id
        WHERE w.target_price IS NOT NULL
          AND ep.price <= w.target_price
    """)

    alerts = []
    for r in rows:
        alerts.append({
            "wish_id":       str(r["wish_id"]),
            "session_id":    r["session_id"],
            "ext_product_id": str(r["ext_product_id"]),
            "product_name":  r["product_name"],
            "current_price": float(r["price"]),
            "target_price":  float(r["target_price"]),
            "savings":       round(float(r["target_price"]) - float(r["price"]), 2),
            "source":        r["source"],
        })

    log.info(f"[PriceAlert] {len(alerts)} items at or below target price")
    return {"total_alerts": len(alerts), "alerts": alerts}


def get_alerts_for_session(session_id: str) -> list[dict]:
    """Return only alerts for a specific session (used by frontend badge)."""
    rows = query("""
        SELECT w.wish_id, w.ext_product_id, w.target_price,
               ep.product_name, ep.price, ep.source, ep.image_url
        FROM ext_wishlist w
        JOIN ext_processed_products ep ON ep.ext_product_id = w.ext_product_id
        WHERE w.session_id = %s
          AND w.target_price IS NOT NULL
          AND ep.price <= w.target_price
        ORDER BY (w.target_price - ep.price) DESC
    """, (session_id,))

    return [{
        "wish_id":        str(r["wish_id"]),
        "ext_product_id": str(r["ext_product_id"]),
        "product_name":   r["product_name"],
        "current_price":  float(r["price"]),
        "target_price":   float(r["target_price"]),
        "savings":        round(float(r["target_price"]) - float(r["price"]), 2),
        "source":         r["source"],
        "image_url":      r.get("image_url", ""),
    } for r in rows]
