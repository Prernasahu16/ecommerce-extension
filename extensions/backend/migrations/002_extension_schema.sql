-- ============================================================
-- EXTENSION SCHEMA — 002_extension_schema.sql
-- NEW TABLES ONLY — zero modification to existing schema
-- Run AFTER 001_schema.sql (existing)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -------------------------------------------------------
-- EXT TABLE 1: standardized_products
-- Clean, de-duplicated data pipeline output
-- Never mixes with raw tables: products, market_prices, etc.
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS standardized_products (
    std_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Canonical fields
    product_name     VARCHAR(250) NOT NULL,
    price            DECIMAL(12,2),
    original_price   DECIMAL(12,2),
    discount         DECIMAL(5,2),
    rating           DECIMAL(3,1),
    reviews          INT DEFAULT 0,
    source           VARCHAR(50) NOT NULL,   -- amazon | flipkart | fakestore | manual
    country          CHAR(2) DEFAULT 'US',   -- IN | US | UK
    currency         CHAR(3) DEFAULT 'USD',
    -- Dedup key: source + source_product_id
    source_product_id VARCHAR(200),
    -- Advanced score (non-destructive; separate from existing value_score)
    advanced_value_score DECIMAL(6,4),
    -- Link back to existing system if matched
    linked_product_id UUID,  -- nullable FK to products.product_id
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_product_id)
);

CREATE INDEX IF NOT EXISTS idx_std_source    ON standardized_products(source);
CREATE INDEX IF NOT EXISTS idx_std_country   ON standardized_products(country);
CREATE INDEX IF NOT EXISTS idx_std_avs       ON standardized_products(advanced_value_score);
CREATE INDEX IF NOT EXISTS idx_std_name      ON standardized_products USING gin (product_name gin_trgm_ops);

-- -------------------------------------------------------
-- EXT TABLE 2: ext_price_history
-- Time-series price tracking linked via std_id
-- Does NOT modify the existing price_history table
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS ext_price_history (
    ext_ph_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    std_id       UUID REFERENCES standardized_products(std_id) ON DELETE CASCADE,
    price        DECIMAL(12,2) NOT NULL,
    original_price DECIMAL(12,2),
    currency     CHAR(3) DEFAULT 'USD',
    source       VARCHAR(50),
    recorded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_extph_std     ON ext_price_history(std_id);
CREATE INDEX IF NOT EXISTS idx_extph_time    ON ext_price_history(recorded_at);

-- -------------------------------------------------------
-- EXT TABLE 3: product_comparisons
-- Cache comparison results between matched products
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_comparisons (
    comparison_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_name      VARCHAR(250),
    results_json    JSONB,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -------------------------------------------------------
-- EXT TABLE 4: user_wishlist  (separate from user_favorites)
-- user_favorites already exists — this adds wishlist intent
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_wishlist (
    wishlist_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   VARCHAR(100) NOT NULL,   -- client-side session, no auth required
    std_id       UUID REFERENCES standardized_products(std_id) ON DELETE CASCADE,
    -- Also support linking to existing products
    product_id   UUID,  -- references products(product_id) — soft FK, no CASCADE
    added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    note         TEXT,
    UNIQUE(session_id, std_id)
);

CREATE INDEX IF NOT EXISTS idx_wl_session ON user_wishlist(session_id);

-- -------------------------------------------------------
-- EXT TABLE 5: saved_products  (separate save feature)
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS saved_products (
    save_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   VARCHAR(100) NOT NULL,
    std_id       UUID REFERENCES standardized_products(std_id) ON DELETE CASCADE,
    product_id   UUID,  -- soft FK to existing products
    saved_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, std_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_session ON saved_products(session_id);

-- -------------------------------------------------------
-- VERIFY
-- -------------------------------------------------------
SELECT table_name, 'extension-created' AS status
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('standardized_products','ext_price_history',
                     'product_comparisons','user_wishlist','saved_products')
ORDER BY table_name;
