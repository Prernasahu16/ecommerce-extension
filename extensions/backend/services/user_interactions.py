# ============================================================
# EXTENSION LAYER — User Interaction Service
# FILE: backend/services/user_interactions.py
# PURPOSE: Save products & wishlist management using browser
#          session_id as the user key.  Stored in ext_user_saves
#          and ext_wishlist ONLY — does not touch existing
#          users or user_favorites tables.
# ============================================================

import logging
from db import get_connection, query

log = logging.getLogger(__name__)


# -------------------------------------------------------
# SAVED PRODUCTS
# -------------------------------------------------------
def save_product(session_id: str, ext_product_id: str, note: str = "") -> dict:
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO ext_user_saves (session_id, ext_product_id, note)
            VALUES (%s, %s, %s)
            ON CONFLICT (session_id, ext_product_id)
            DO UPDATE SET note = EXCLUDED.note
            RETURNING save_id
        """, (session_id, ext_product_id, note))
        row = cur.fetchone()
        conn.commit()
        return {"success": True, "save_id": str(row[0]) if row else None}
    except Exception as e:
        conn.rollback()
        log.error(f"[UserInteractions] save_product error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def unsave_product(session_id: str, ext_product_id: str) -> dict:
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            DELETE FROM ext_user_saves
            WHERE session_id = %s AND ext_product_id = %s
        """, (session_id, ext_product_id))
        conn.commit()
        return {"success": True, "deleted": cur.rowcount}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def get_saved_products(session_id: str) -> list[dict]:
    return query("""
        SELECT s.save_id, s.note, s.saved_at,
               ep.ext_product_id, ep.product_name, ep.price, ep.original_price,
               ep.discount, ep.rating, ep.reviews, ep.source, ep.country,
               ep.category, ep.image_url, ep.product_url,
               eas.advanced_value_score
        FROM ext_user_saves s
        JOIN ext_processed_products ep ON ep.ext_product_id = s.ext_product_id
        LEFT JOIN ext_advanced_scores eas ON eas.ext_product_id = s.ext_product_id
        WHERE s.session_id = %s
        ORDER BY s.saved_at DESC
    """, (session_id,))


# -------------------------------------------------------
# WISHLIST
# -------------------------------------------------------
def add_to_wishlist(session_id: str, ext_product_id: str,
                    target_price: float = None) -> dict:
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO ext_wishlist (session_id, ext_product_id, target_price)
            VALUES (%s, %s, %s)
            ON CONFLICT (session_id, ext_product_id)
            DO UPDATE SET target_price = EXCLUDED.target_price
            RETURNING wish_id
        """, (session_id, ext_product_id, target_price))
        row = cur.fetchone()
        conn.commit()
        return {"success": True, "wish_id": str(row[0]) if row else None}
    except Exception as e:
        conn.rollback()
        log.error(f"[UserInteractions] add_to_wishlist error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def remove_from_wishlist(session_id: str, ext_product_id: str) -> dict:
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            DELETE FROM ext_wishlist
            WHERE session_id = %s AND ext_product_id = %s
        """, (session_id, ext_product_id))
        conn.commit()
        return {"success": True, "deleted": cur.rowcount}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def get_wishlist(session_id: str) -> list[dict]:
    return query("""
        SELECT w.wish_id, w.target_price, w.added_at,
               ep.ext_product_id, ep.product_name, ep.price, ep.original_price,
               ep.discount, ep.rating, ep.reviews, ep.source, ep.country,
               ep.category, ep.image_url, ep.product_url,
               eas.advanced_value_score,
               CASE
                   WHEN w.target_price IS NOT NULL AND ep.price <= w.target_price
                   THEN TRUE ELSE FALSE
               END AS target_reached
        FROM ext_wishlist w
        JOIN ext_processed_products ep ON ep.ext_product_id = w.ext_product_id
        LEFT JOIN ext_advanced_scores eas ON eas.ext_product_id = w.ext_product_id
        WHERE w.session_id = %s
        ORDER BY w.added_at DESC
    """, (session_id,))


def check_membership(session_id: str, ext_product_ids: list[str]) -> dict:
    """
    Returns saved/wishlist status for a list of ext_product_ids.
    Used by the UI to show correct button states.
    """
    if not ext_product_ids:
        return {}

    saved = {
        r["ext_product_id"]
        for r in query(
            "SELECT ext_product_id FROM ext_user_saves WHERE session_id=%s AND ext_product_id=ANY(%s)",
            (session_id, ext_product_ids)
        )
    }
    wished = {
        r["ext_product_id"]
        for r in query(
            "SELECT ext_product_id FROM ext_wishlist WHERE session_id=%s AND ext_product_id=ANY(%s)",
            (session_id, ext_product_ids)
        )
    }

    return {
        pid: {"saved": pid in saved, "wishlisted": pid in wished}
        for pid in ext_product_ids
    }
