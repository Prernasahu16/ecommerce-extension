-- ============================================================
-- EXTENSION AUTH SCHEMA — 003_auth_schema.sql
-- NEW TABLE ONLY — ext_users
-- Run AFTER 002_extensions_schema.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS ext_users (
    user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    display_name  VARCHAR(100),
    role          VARCHAR(20) DEFAULT 'user',  -- user | admin
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ext_users_email ON ext_users(email);

-- Add optional user_id FK to wishlist and saves (nullable — session still works)
ALTER TABLE ext_user_saves ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES ext_users(user_id) ON DELETE SET NULL;
ALTER TABLE ext_wishlist   ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES ext_users(user_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_ext_saves_user  ON ext_user_saves(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ext_wish_user   ON ext_wishlist(user_id)   WHERE user_id IS NOT NULL;
