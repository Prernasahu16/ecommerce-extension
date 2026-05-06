# ============================================================
# EXTENSION LAYER — api/ext_routes.py  (FINAL)
# All new endpoints live at /api/ext/*
# Wires: services/data_pipeline | services/connectors |
#        services/comparison_engine | services/user_interactions |
#        ml/advanced_score
# Zero modification to existing api/routes.py
# ============================================================

from flask import Blueprint, request, jsonify
import logging

log = logging.getLogger(__name__)

ext_bp = Blueprint("ext_api", __name__, url_prefix="/api/ext")


def _ok(data, **kw):
    return jsonify({"success": True, "data": data, **kw})

def _err(msg, code=400):
    return jsonify({"success": False, "error": msg}), code

def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ============================================================
# 1. GLOBAL SEARCH
# GET /api/ext/search?q=&country=&source=&min_price=&max_price=
#                    &min_rating=&sort=&order=&page=&limit=
# ============================================================
@ext_bp.route("/search")
def ext_search():
    q          = request.args.get("q", "").strip()
    country    = request.args.get("country", "").strip().upper()
    source     = request.args.get("source", "").strip()
    min_price  = _safe_float(request.args.get("min_price"))
    max_price  = _safe_float(request.args.get("max_price"))
    min_rating = _safe_float(request.args.get("min_rating"))
    sort       = request.args.get("sort", "advanced_value_score")
    order      = request.args.get("order", "desc").upper()
    page       = max(1, request.args.get("page", 1, type=int))
    limit      = min(100, request.args.get("limit", 20, type=int))
    offset     = (page - 1) * limit

    allowed_sorts  = {"advanced_value_score", "price", "rating", "discount", "reviews"}
    allowed_orders = {"ASC", "DESC"}
    if sort  not in allowed_sorts:  sort  = "advanced_value_score"
    if order not in allowed_orders: order = "DESC"

    from db import query
    conditions, params = ["1=1"], []
    if q:
        conditions.append("LOWER(ep.product_name) LIKE %s")
        params.append(f"%{q.lower()}%")
    if country in ("US", "IN", "GB"):
        conditions.append("ep.country = %s")
        params.append(country)
    if source:
        conditions.append("LOWER(ep.source) LIKE %s")
        params.append(f"%{source.lower()}%")
    if min_price is not None:
        conditions.append("ep.price >= %s"); params.append(min_price)
    if max_price is not None:
        conditions.append("ep.price <= %s"); params.append(max_price)
    if min_rating is not None:
        conditions.append("ep.rating >= %s"); params.append(min_rating)

    where = " AND ".join(conditions)
    sort_col_map = {
        "advanced_value_score": "eas.advanced_value_score",
        "price":    "ep.price",
        "rating":   "ep.rating",
        "discount": "ep.discount",
        "reviews":  "ep.reviews",
    }
    sort_col = sort_col_map[sort]

    total_row = query(
        f"SELECT COUNT(*) AS n FROM ext_processed_products ep WHERE {where}",
        params, fetch="one"
    )
    total = int(total_row["n"]) if total_row else 0

    rows = query(f"""
        SELECT ep.ext_product_id, ep.product_name, ep.price, ep.original_price,
               ep.discount, ep.rating, ep.reviews, ep.source, ep.country,
               ep.category, ep.image_url, ep.product_url,
               eas.advanced_value_score
        FROM ext_processed_products ep
        LEFT JOIN ext_advanced_scores eas ON eas.ext_product_id = ep.ext_product_id
        WHERE {where}
        ORDER BY {sort_col} {order} NULLS LAST
        LIMIT %s OFFSET %s
    """, params + [limit, offset])

    return _ok(
        [_fmt_product(r) for r in rows],
        total=total, page=page, limit=limit,
        pages=max(1, (total - 1) // limit + 1) if total else 1,
    )


# ============================================================
# 2. INGEST FROM EXTERNAL PLATFORM
# POST /api/ext/ingest  { "source": "amazon|flipkart|fakestore",
#                         "query": "...", "country": "US", "limit": 20 }
# ============================================================
@ext_bp.route("/ingest", methods=["POST"])
def ext_ingest():
    body    = request.get_json() or {}
    source  = body.get("source", "fakestore").strip().lower()
    q       = body.get("query", "electronics").strip()
    country = body.get("country", "US").strip().upper()
    limit   = min(50, int(body.get("limit", 20)))

    try:
        from services.connectors import get_connector
        connector = get_connector(source, country)
    except ValueError as e:
        return _err(str(e))

    try:
        raw = connector.fetch(query=q, limit=limit)
    except Exception as e:
        log.error(f"[ext_ingest] Connector error: {e}")
        return _err(f"Connector fetch failed: {e}")

    try:
        from services.data_pipeline import ingest
        result = ingest(raw, source=source, country=country)
    except Exception as e:
        log.error(f"[ext_ingest] Pipeline error: {e}")
        return _err(f"Pipeline error: {e}")

    # Async scoring after ingestion
    import threading
    def _score():
        try:
            from ml.advanced_score import compute_advanced_scores
            compute_advanced_scores()
        except Exception as ex:
            log.warning(f"[ext_ingest] Background scoring error: {ex}")
    threading.Thread(target=_score, daemon=True).start()

    return _ok({
        "source": source, "country": country, "query": q,
        "pipeline": result,
        "message": f"Ingested {result['inserted']} new, updated {result['updated']}. Scoring running in background."
    })


# ============================================================
# 3. COMPUTE ADVANCED VALUE SCORES
# POST /api/ext/compute-scores  { "price": 0.35, "rating": 0.30, ... }
# ============================================================
@ext_bp.route("/compute-scores", methods=["POST"])
def ext_compute_scores():
    body = request.get_json() or {}
    weights = {k: float(v) for k, v in body.items()
               if k in ("price", "rating", "reviews", "discount")}
    try:
        from ml.advanced_score import compute_advanced_scores
        count = compute_advanced_scores(weights or None)
        return _ok({"scored": count, "weights_used": weights or "defaults"})
    except Exception as e:
        return _err(str(e), 500)


# ============================================================
# 4. COMPARISON ENGINE
# GET /api/ext/compare?q=laptop&country=IN&max_results=20
# GET /api/ext/compare/<ext_product_id>
# ============================================================
@ext_bp.route("/compare")
def ext_compare_keyword():
    q           = request.args.get("q", "").strip()
    country     = request.args.get("country", "").strip().upper() or None
    max_results = min(50, request.args.get("max_results", 20, type=int))
    if not q:
        return _err("Query parameter 'q' is required")
    from services.comparison_engine import compare_by_keyword
    return _ok(compare_by_keyword(q, country=country, max_results=max_results))


@ext_bp.route("/compare/<ext_product_id>")
def ext_compare_product(ext_product_id):
    max_results = min(20, request.args.get("max_results", 10, type=int))
    from services.comparison_engine import compare_product
    result = compare_product(ext_product_id, max_results=max_results)
    if "error" in result:
        return _err(result["error"], 404)
    return _ok(result)


# ============================================================
# 5. PRICE HISTORY
# GET /api/ext/price-history/<ext_product_id>
# ============================================================
@ext_bp.route("/price-history/<ext_product_id>")
def ext_price_history(ext_product_id):
    from db import query
    rows = query("""
        SELECT price, original_price, source, recorded_at
        FROM ext_price_history
        WHERE ext_product_id = %s
        ORDER BY recorded_at ASC
        LIMIT 180
    """, (ext_product_id,))
    return _ok([{
        "price":          float(r["price"]),
        "original_price": float(r["original_price"]) if r.get("original_price") else None,
        "source":         r["source"],
        "recorded_at":    r["recorded_at"].isoformat() if r.get("recorded_at") else None,
    } for r in rows])


# ============================================================
# 6. SAVED PRODUCTS
# GET    /api/ext/saved/<session_id>
# POST   /api/ext/saved/<session_id>   { "ext_product_id": "...", "note": "" }
# DELETE /api/ext/saved/<session_id>/<ext_product_id>
# ============================================================
@ext_bp.route("/saved/<session_id>", methods=["GET"])
def get_saved(session_id):
    from services.user_interactions import get_saved_products
    return _ok([_fmt_saved(r) for r in get_saved_products(session_id)])


@ext_bp.route("/saved/<session_id>", methods=["POST"])
def save_product(session_id):
    body           = request.get_json() or {}
    ext_product_id = body.get("ext_product_id", "").strip()
    note           = body.get("note", "")
    if not ext_product_id:
        return _err("'ext_product_id' is required")
    from services.user_interactions import save_product as svc_save
    result = svc_save(session_id, ext_product_id, note)
    return _ok(result) if result["success"] else _err(result.get("error"), 500)


@ext_bp.route("/saved/<session_id>/<ext_product_id>", methods=["DELETE"])
def unsave_product(session_id, ext_product_id):
    from services.user_interactions import unsave_product
    result = unsave_product(session_id, ext_product_id)
    return _ok(result) if result["success"] else _err(result.get("error"), 500)


# ============================================================
# 7. WISHLIST
# GET    /api/ext/wishlist/<session_id>
# POST   /api/ext/wishlist/<session_id>  { "ext_product_id": "...", "target_price": 99.0 }
# DELETE /api/ext/wishlist/<session_id>/<ext_product_id>
# ============================================================
@ext_bp.route("/wishlist/<session_id>", methods=["GET"])
def get_wishlist(session_id):
    from services.user_interactions import get_wishlist
    return _ok([_fmt_wishlist(r) for r in get_wishlist(session_id)])


@ext_bp.route("/wishlist/<session_id>", methods=["POST"])
def add_wishlist(session_id):
    body           = request.get_json() or {}
    ext_product_id = body.get("ext_product_id", "").strip()
    target_price   = _safe_float(body.get("target_price"))
    if not ext_product_id:
        return _err("'ext_product_id' is required")
    from services.user_interactions import add_to_wishlist
    result = add_to_wishlist(session_id, ext_product_id, target_price)
    return _ok(result) if result["success"] else _err(result.get("error"), 500)


@ext_bp.route("/wishlist/<session_id>/<ext_product_id>", methods=["DELETE"])
def remove_wishlist(session_id, ext_product_id):
    from services.user_interactions import remove_from_wishlist
    result = remove_from_wishlist(session_id, ext_product_id)
    return _ok(result) if result["success"] else _err(result.get("error"), 500)


# ============================================================
# 8. BATCH MEMBERSHIP CHECK
# POST /api/ext/membership/<session_id>  { "ids": ["...", "..."] }
# ============================================================
@ext_bp.route("/membership/<session_id>", methods=["POST"])
def check_membership(session_id):
    body = request.get_json() or {}
    ids  = body.get("ids", [])
    if not isinstance(ids, list):
        return _err("'ids' must be a list")
    from services.user_interactions import check_membership as svc_check
    return _ok(svc_check(session_id, ids))


# ============================================================
# 9. EXTENSION STATS
# GET /api/ext/stats
# ============================================================
@ext_bp.route("/stats")
def ext_stats():
    from db import query
    overview = query("""
        SELECT COUNT(*)                            AS total_products,
               COUNT(DISTINCT ep.source)           AS total_sources,
               COUNT(DISTINCT ep.country)          AS total_countries,
               ROUND(AVG(ep.price)::NUMERIC,2)     AS avg_price,
               ROUND(AVG(ep.rating)::NUMERIC,2)    AS avg_rating,
               ROUND(AVG(ep.discount)::NUMERIC,2)  AS avg_discount,
               ROUND(AVG(eas.advanced_value_score)::NUMERIC,4) AS avg_adv_score
        FROM ext_processed_products ep
        LEFT JOIN ext_advanced_scores eas ON eas.ext_product_id = ep.ext_product_id
    """, fetch="one")
    by_source = query("""
        SELECT ep.source, ep.country, COUNT(*) AS count,
               ROUND(AVG(ep.price)::NUMERIC,2)  AS avg_price,
               ROUND(AVG(ep.rating)::NUMERIC,2) AS avg_rating,
               ROUND(AVG(eas.advanced_value_score)::NUMERIC,4) AS avg_adv_score
        FROM ext_processed_products ep
        LEFT JOIN ext_advanced_scores eas ON eas.ext_product_id = ep.ext_product_id
        GROUP BY ep.source, ep.country
        ORDER BY count DESC
    """)
    return _ok({"overview": overview, "by_source": by_source})


# ============================================================
# SERIALIZERS
# ============================================================
def _fmt_product(r: dict) -> dict:
    return {
        "ext_product_id":       str(r["ext_product_id"]),
        "product_name":         r["product_name"],
        "price":                float(r["price"])                    if r.get("price")                else None,
        "original_price":       float(r["original_price"])          if r.get("original_price")       else None,
        "discount":             float(r["discount"])                 if r.get("discount")             else None,
        "rating":               float(r["rating"])                   if r.get("rating")               else None,
        "reviews":              int(r["reviews"])                    if r.get("reviews")              else 0,
        "source":               r.get("source", ""),
        "country":              r.get("country", ""),
        "category":             r.get("category", ""),
        "image_url":            r.get("image_url", ""),
        "product_url":          r.get("product_url", ""),
        "advanced_value_score": float(r["advanced_value_score"])     if r.get("advanced_value_score") else None,
    }

def _fmt_saved(r: dict) -> dict:
    p = _fmt_product(r)
    p["save_id"]  = str(r["save_id"])
    p["note"]     = r.get("note", "")
    p["saved_at"] = r["saved_at"].isoformat() if r.get("saved_at") else None
    return p

def _fmt_wishlist(r: dict) -> dict:
    p = _fmt_product(r)
    p["wish_id"]       = str(r["wish_id"])
    p["target_price"]  = float(r["target_price"]) if r.get("target_price") else None
    p["target_reached"] = bool(r.get("target_reached", False))
    p["added_at"]      = r["added_at"].isoformat() if r.get("added_at") else None
    return p


# ============================================================
# FEATURE ADDITIONS — appended, no existing code changed
# ============================================================

# ============================================================
# A. PAGINATION — saved & wishlist (new paginated variants)
# GET /api/ext/saved/<session_id>/page?page=1&limit=20
# GET /api/ext/wishlist/<session_id>/page?page=1&limit=20
# Default params keep original /saved/<id> GET unchanged.
# ============================================================
@ext_bp.route("/saved/<session_id>/page", methods=["GET"])
def get_saved_paged(session_id):
    page   = max(1, request.args.get("page",  1, type=int))
    limit  = min(100, request.args.get("limit", 20, type=int))
    offset = (page - 1) * limit

    from db import query as db_query
    total_row = db_query(
        "SELECT COUNT(*) AS n FROM ext_user_saves WHERE session_id = %s",
        (session_id,), fetch="one"
    )
    total = int(total_row["n"]) if total_row else 0

    rows = db_query("""
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
        LIMIT %s OFFSET %s
    """, (session_id, limit, offset))

    return _ok(
        [_fmt_saved(r) for r in rows],
        total=total, page=page, limit=limit,
        pages=max(1, (total - 1) // limit + 1) if total else 1,
    )


@ext_bp.route("/wishlist/<session_id>/page", methods=["GET"])
def get_wishlist_paged(session_id):
    page   = max(1, request.args.get("page",  1, type=int))
    limit  = min(100, request.args.get("limit", 20, type=int))
    offset = (page - 1) * limit

    from db import query as db_query
    total_row = db_query(
        "SELECT COUNT(*) AS n FROM ext_wishlist WHERE session_id = %s",
        (session_id,), fetch="one"
    )
    total = int(total_row["n"]) if total_row else 0

    rows = db_query("""
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
        LIMIT %s OFFSET %s
    """, (session_id, limit, offset))

    return _ok(
        [_fmt_wishlist(r) for r in rows],
        total=total, page=page, limit=limit,
        pages=max(1, (total - 1) // limit + 1) if total else 1,
    )


# ============================================================
# B. COMPARISON CACHING — writes into ext_comparison_groups
#    and ext_comparison_members (tables exist from migration).
# GET /api/ext/compare/cached?q=laptop&country=US
# GET /api/ext/compare/groups  (list cached groups)
# ============================================================
@ext_bp.route("/compare/cached")
def ext_compare_cached():
    """
    Comparison with DB caching.
    First checks ext_comparison_groups for recent result (< 6h).
    On miss: runs live compare_by_keyword, then writes to cache tables.
    """
    q           = request.args.get("q", "").strip()
    country     = request.args.get("country", "").strip().upper() or None
    max_results = min(50, request.args.get("max_results", 20, type=int))
    if not q:
        return _err("Query parameter 'q' is required")

    from db import query as db_query, get_connection

    # Cache lookup — fresh within 6 hours
    cache_key = f"{q.lower()}|{country or 'ALL'}"
    cached = db_query("""
        SELECT group_id, group_name, cached_result, created_at
        FROM ext_comparison_groups
        WHERE keyword = %s
          AND created_at > NOW() - INTERVAL '6 hours'
        ORDER BY created_at DESC
        LIMIT 1
    """, (cache_key,), fetch="one")

    if cached and cached.get("cached_result"):
        import json
        result = json.loads(cached["cached_result"])
        result["_cache"] = {
            "hit":        True,
            "group_id":   str(cached["group_id"]),
            "cached_at":  cached["created_at"].isoformat(),
        }
        return _ok(result)

    # Cache miss — run live comparison
    from services.comparison_engine import compare_by_keyword
    result = compare_by_keyword(q, country=country, max_results=max_results)

    # Write to cache
    _write_comparison_cache(q, cache_key, country, result, db_query, get_connection)
    result["_cache"] = {"hit": False}
    return _ok(result)


def _write_comparison_cache(q, cache_key, country, result, db_query, get_connection):
    """Write comparison results into ext_comparison_groups + ext_comparison_members."""
    import json
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO ext_comparison_groups
                (group_name, category, keyword, cached_result)
            VALUES (%s, %s, %s, %s)
            RETURNING group_id
        """, (
            q[:300],
            country or "ALL",
            cache_key,
            json.dumps(result),
        ))
        row      = cur.fetchone()
        group_id = row[0] if row else None

        if group_id and result.get("results"):
            for item in result["results"]:
                pid = item.get("ext_product_id")
                if not pid:
                    continue
                try:
                    cur.execute("""
                        INSERT INTO ext_comparison_members
                            (group_id, ext_product_id, is_lowest_price, is_best_rating)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (group_id, ext_product_id) DO NOTHING
                    """, (
                        group_id, pid,
                        item.get("is_lowest_price", False),
                        item.get("is_best_rating",  False),
                    ))
                except Exception:
                    pass  # stale product_id — skip silently

        conn.commit()
    except Exception as e:
        conn.rollback()
        log.warning(f"[CompareCache] Write failed: {e}")
    finally:
        cur.close()
        conn.close()


@ext_bp.route("/compare/groups")
def ext_compare_groups():
    """GET /api/ext/compare/groups — list recent cached comparison groups."""
    limit = min(50, request.args.get("limit", 20, type=int))
    from db import query as db_query
    rows = db_query("""
        SELECT g.group_id, g.group_name, g.keyword, g.category, g.created_at,
               COUNT(m.member_id) AS member_count
        FROM ext_comparison_groups g
        LEFT JOIN ext_comparison_members m ON m.group_id = g.group_id
        GROUP BY g.group_id
        ORDER BY g.created_at DESC
        LIMIT %s
    """, (limit,))
    return _ok([{
        "group_id":    str(r["group_id"]),
        "group_name":  r["group_name"],
        "keyword":     r["keyword"],
        "category":    r["category"],
        "created_at":  r["created_at"].isoformat() if r.get("created_at") else None,
        "member_count": int(r["member_count"]),
    } for r in rows])


# ============================================================
# C. AUTH ENDPOINTS — JWT register / login / me / refresh
# POST /api/ext/auth/register  { email, password, display_name }
# POST /api/ext/auth/login     { email, password }
# GET  /api/ext/auth/me        (Bearer token required)
# POST /api/ext/auth/refresh   (Bearer token required)
# ============================================================
@ext_bp.route("/auth/register", methods=["POST"])
def auth_register():
    body     = request.get_json() or {}
    email    = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    name     = (body.get("display_name") or email.split("@")[0])[:100]

    if not email or "@" not in email:
        return _err("Valid email required")
    if len(password) < 8:
        return _err("Password must be at least 8 characters")

    from auth.jwt_auth import hash_password, generate_token
    from db import get_connection, query as db_query

    existing = db_query(
        "SELECT user_id FROM ext_users WHERE email = %s", (email,), fetch="one"
    )
    if existing:
        return _err("Email already registered", 409)

    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO ext_users (email, password_hash, display_name)
            VALUES (%s, %s, %s)
            RETURNING user_id
        """, (email, hash_password(password), name))
        user_id = str(cur.fetchone()[0])
        conn.commit()
    except Exception as e:
        conn.rollback()
        return _err(f"Registration failed: {e}", 500)
    finally:
        cur.close()
        conn.close()

    token = generate_token(user_id, email)
    return _ok({"user_id": user_id, "email": email, "display_name": name, "token": token}), 201


@ext_bp.route("/auth/login", methods=["POST"])
def auth_login():
    body     = request.get_json() or {}
    email    = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()

    if not email or not password:
        return _err("Email and password required")

    from auth.jwt_auth import verify_password, generate_token
    from db import query as db_query, get_connection

    user = db_query(
        "SELECT user_id, password_hash, display_name, role FROM ext_users WHERE email = %s",
        (email,), fetch="one"
    )
    if not user or not verify_password(password, user["password_hash"]):
        return _err("Invalid email or password", 401)

    # Update last_login
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "UPDATE ext_users SET last_login = NOW() WHERE user_id = %s",
            (user["user_id"],)
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    token = generate_token(str(user["user_id"]), email, user.get("role", "user"))
    return _ok({
        "user_id":      str(user["user_id"]),
        "email":        email,
        "display_name": user.get("display_name", ""),
        "role":         user.get("role", "user"),
        "token":        token,
    })


@ext_bp.route("/auth/me", methods=["GET"])
def auth_me():
    from auth.jwt_auth import require_jwt, decode_token

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return _err("JWT required", 401)
    payload = decode_token(auth_header[7:])
    if not payload:
        return _err("Invalid or expired token", 401)

    from db import query as db_query
    user = db_query(
        "SELECT user_id, email, display_name, role, created_at, last_login FROM ext_users WHERE user_id = %s",
        (payload["sub"],), fetch="one"
    )
    if not user:
        return _err("User not found", 404)

    return _ok({
        "user_id":      str(user["user_id"]),
        "email":        user["email"],
        "display_name": user.get("display_name", ""),
        "role":         user.get("role", "user"),
        "created_at":   user["created_at"].isoformat() if user.get("created_at") else None,
        "last_login":   user["last_login"].isoformat()  if user.get("last_login")  else None,
    })


@ext_bp.route("/auth/refresh", methods=["POST"])
def auth_refresh():
    from auth.jwt_auth import decode_token, generate_token

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return _err("JWT required", 401)
    payload = decode_token(auth_header[7:])
    if not payload:
        return _err("Invalid or expired token — please log in again", 401)

    new_token = generate_token(payload["sub"], payload["email"], payload.get("role", "user"))
    return _ok({"token": new_token})


# ============================================================
# D. PRICE DROP ALERTS
# GET /api/ext/alerts/<session_id>   — alerts for one session
# GET /api/ext/alerts/all            — admin: all triggered alerts
# ============================================================
@ext_bp.route("/alerts/<session_id>", methods=["GET"])
def get_alerts(session_id):
    from services.price_alert import get_alerts_for_session
    alerts = get_alerts_for_session(session_id)
    return _ok(alerts, count=len(alerts))


@ext_bp.route("/alerts/all", methods=["GET"])
def get_all_alerts():
    from services.price_alert import check_all_alerts
    return _ok(check_all_alerts())


# ============================================================
# E. USER-LINKED SAVED + WISHLIST (JWT users)
# After login, re-associate session data to real user_id.
# POST /api/ext/auth/link-session
# Body: { "session_id": "sess_xxx" }   Bearer token required.
# ============================================================
@ext_bp.route("/auth/link-session", methods=["POST"])
def link_session_to_user():
    from auth.jwt_auth import decode_token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return _err("JWT required", 401)
    payload = decode_token(auth_header[7:])
    if not payload:
        return _err("Invalid or expired token", 401)

    body       = request.get_json() or {}
    session_id = body.get("session_id", "").strip()
    if not session_id:
        return _err("session_id required")

    user_id = payload["sub"]
    from db import get_connection
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "UPDATE ext_user_saves SET user_id = %s WHERE session_id = %s AND user_id IS NULL",
            (user_id, session_id)
        )
        saves_linked = cur.rowcount
        cur.execute(
            "UPDATE ext_wishlist SET user_id = %s WHERE session_id = %s AND user_id IS NULL",
            (user_id, session_id)
        )
        wish_linked = cur.rowcount
        conn.commit()
        return _ok({"saves_linked": saves_linked, "wishlist_linked": wish_linked})
    except Exception as e:
        conn.rollback()
        return _err(str(e), 500)
    finally:
        cur.close()
        conn.close()
