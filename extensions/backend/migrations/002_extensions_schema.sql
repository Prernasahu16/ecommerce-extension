-- ============================================================
-- EXTENSION LAYER — Migration 002
-- FILE: backend/migrations/002_extensions_schema.sql
-- PURPOSE: Adds NEW tables for the extension layer.
--          NEVER modifies tables created in 001_schema.sql.
-- Run AFTER 001_schema.sql is applied.
-- ============================================================

-- -------------------------------------------------------
-- EXT TABLE 1: ext_processed_products
-- Standardized, deduplicated product catalogue from all sources.
-- Keeps original dataset completely untouched.
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS ext_processed_products (
    ext_product_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key       VARCHAR(120) UNIQUE NOT NULL, -- dedup key: source + external_id
    product_name     VARCHAR(300) NOT NULL,
    price            DECIMAL(12,2),
    original_price   DECIMAL(12,2),
    discount         DECIMAL(5,2),
    rating           DECIMAL(3,1),
    reviews          INT DEFAULT 0,
    source           VARCHAR(40) NOT NULL,  -- amazon | flipkart | fakestore | manual
    country          CHAR(2) DEFAULT 'US',  -- US | IN | GB
    category         VARCHAR(100),
    image_url        TEXT,
    product_url      TEXT,
    raw_external_id  VARCHAR(200),
    ingested_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ext_pp_source   ON ext_processed_products(source);
CREATE INDEX IF NOT EXISTS idx_ext_pp_country  ON ext_processed_products(country);
CREATE INDEX IF NOT EXISTS idx_ext_pp_name     ON ext_processed_products USING gin (product_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ext_pp_category ON ext_processed_products(category);

-- -------------------------------------------------------
-- EXT TABLE 2: ext_advanced_scores
-- Stores advanced_value_score without touching value_scores.
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS ext_advanced_scores (
    adv_score_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ext_product_id     UUID REFERENCES ext_processed_products(ext_product_id) ON DELETE CASCADE,
    price_factor       DECIMAL(6,4),
    rating_factor      DECIMAL(6,4),
    reviews_factor     DECIMAL(6,4),
    discount_factor    DECIMAL(6,4),
    advanced_value_score DECIMAL(6,4) NOT NULL,
    computed_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ext_adv_product_uniq ON ext_advanced_scores(ext_product_id);
CREATE INDEX IF NOT EXISTS idx_ext_adv_score ON ext_advanced_scores(advanced_value_score);

-- -------------------------------------------------------
-- EXT TABLE 3: ext_price_history
-- Separate price history table for ext products.
-- (existing price_history table in 001 is for core products)
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS ext_price_history (
    ph_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ext_product_id UUID REFERENCES ext_processed_products(ext_product_id) ON DELETE CASCADE,
    price          DECIMAL(12,2) NOT NULL,
    original_price DECIMAL(12,2),
    source         VARCHAR(40),
    recorded_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ext_ph_product  ON ext_price_history(ext_product_id);
CREATE INDEX IF NOT EXISTS idx_ext_ph_time     ON ext_price_history(recorded_at);

-- -------------------------------------------------------
-- EXT TABLE 4: ext_comparison_groups
-- Clusters of similar products for comparison engine.
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS ext_comparison_groups (
    group_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_name       VARCHAR(300) NOT NULL,
    category         VARCHAR(100),
    keyword          VARCHAR(200),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ext_comparison_members (
    member_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id       UUID REFERENCES ext_comparison_groups(group_id) ON DELETE CASCADE,
    ext_product_id UUID REFERENCES ext_processed_products(ext_product_id) ON DELETE CASCADE,
    is_lowest_price  BOOLEAN DEFAULT FALSE,
    is_best_rating   BOOLEAN DEFAULT FALSE,
    added_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, ext_product_id)
);

CREATE INDEX IF NOT EXISTS idx_ext_cm_group ON ext_comparison_members(group_id);

-- -------------------------------------------------------
-- EXT TABLE 5: ext_user_saves & ext_wishlist
-- User interaction extension — completely separate from
-- existing user_favorites table in 001_schema.sql.
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS ext_user_saves (
    save_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     VARCHAR(120) NOT NULL,  -- browser session or user key
    ext_product_id UUID REFERENCES ext_processed_products(ext_product_id) ON DELETE CASCADE,
    note           TEXT,
    saved_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, ext_product_id)
);

CREATE TABLE IF NOT EXISTS ext_wishlist (
    wish_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     VARCHAR(120) NOT NULL,
    ext_product_id UUID REFERENCES ext_processed_products(ext_product_id) ON DELETE CASCADE,
    target_price   DECIMAL(12,2),
    added_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, ext_product_id)
);

CREATE INDEX IF NOT EXISTS idx_ext_saves_session   ON ext_user_saves(session_id);
CREATE INDEX IF NOT EXISTS idx_ext_wish_session    ON ext_wishlist(session_id);

-- -------------------------------------------------------
-- VERIFY
-- -------------------------------------------------------
SELECT table_name, 'ext_created' AS status
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE 'ext_%'
ORDER BY table_name;
