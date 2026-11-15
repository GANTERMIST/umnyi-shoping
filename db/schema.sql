-- «Умный Шопинг»: схема БД для PostgreSQL (та же, что app/db.py создаёт в SQLite).
-- psql -d smartshop -f db/schema.sql

CREATE TABLE IF NOT EXISTS product (
    id               SERIAL PRIMARY KEY,
    steam_appid      INTEGER UNIQUE,              -- по нему склеиваем предложения разных магазинов
    title            TEXT NOT NULL,
    title_norm       TEXT NOT NULL,               -- нижний регистр, без знаков — для поиска
    genres           JSONB NOT NULL DEFAULT '[]',
    image            TEXT,
    metacritic       SMALLINT,
    steam_review_pct SMALLINT,
    steam_reviews    INTEGER,
    release          TEXT,
    updated_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_product_title ON product (title_norm);

CREATE TABLE IF NOT EXISTS store (
    id       SERIAL PRIMARY KEY,
    name     TEXT UNIQUE NOT NULL,                -- plati.market, Steam, GOG, Humble Store…
    api_type TEXT NOT NULL                        -- plati | cheapshark | ggsel
);

CREATE TABLE IF NOT EXISTS offer (
    id            TEXT PRIMARY KEY,               -- «магазин:внешний id», напр. plati:3412257, gog:1245620
    product_id    INTEGER REFERENCES product(id) ON DELETE SET NULL,  -- NULL для не-Steam товаров (пополнения)
    store_id      INTEGER NOT NULL REFERENCES store(id),
    title         TEXT NOT NULL,
    price         NUMERIC(12, 2) NOT NULL,        -- всегда в рублях
    currency      CHAR(3) NOT NULL DEFAULT 'RUB',
    url           TEXT NOT NULL,
    seller        TEXT,
    seller_rating REAL,
    sold          INTEGER,
    reviews_pos   INTEGER,
    reviews_neg   INTEGER,
    returns       INTEGER,
    kind          TEXT NOT NULL CHECK (kind IN ('ключ','гифт','магазин','аккаунт','пополнение','другое')),
    platform      TEXT NOT NULL,
    trusted       BOOLEAN NOT NULL,
    trust_score   REAL NOT NULL CHECK (trust_score BETWEEN 0 AND 1),
    image         TEXT,
    region        TEXT,                           -- RU / CIS / GLOBAL / KZ / TR / EU / NO_RU
    old_price     NUMERIC(12, 2),
    note          TEXT,
    updated_at    TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_offer_product ON offer (product_id);

CREATE TABLE IF NOT EXISTS price_history (
    offer_id   TEXT NOT NULL REFERENCES offer(id) ON DELETE CASCADE,
    price      NUMERIC(12, 2) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL               -- пишется только при изменении цены
);
CREATE INDEX IF NOT EXISTS ix_ph ON price_history (offer_id, fetched_at);

CREATE TABLE IF NOT EXISTS app_user (
    id            SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    name          TEXT,
    pw_hash       TEXT NOT NULL,                  -- PBKDF2-SHA256, 200 000 итераций
    pw_salt       TEXT NOT NULL,
    failed_logins SMALLINT NOT NULL DEFAULT 0,
    locked_until  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_session (
    token_hash TEXT PRIMARY KEY,                  -- SHA-256 токена; сам токен в базе не хранится
    user_id    INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS user_data (
    user_id   INTEGER PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
    profile   JSONB NOT NULL DEFAULT '{}',        -- бюджет, платформа, типы, регион
    favorites JSONB NOT NULL DEFAULT '[]'         -- [{offer_id, title, price (на момент добавления), appid, added_at}]
);
