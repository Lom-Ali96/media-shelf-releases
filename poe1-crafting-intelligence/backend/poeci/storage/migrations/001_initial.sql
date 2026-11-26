-- Milestone 1 schema. Game data itself lives in versioned JSON snapshots
-- (data/snapshots/<game version>/); this database holds user and market state.

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Every version observation (imported data, remote data, league list, ...)
CREATE TABLE IF NOT EXISTS version_checks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT NOT NULL,
    kind       TEXT NOT NULL,     -- 'remote_game_data', 'imported_game_data', 'leagues'
    value      TEXT NOT NULL,
    source     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_version_checks_kind ON version_checks(kind, checked_at);

-- One row per market fetch; raw payload kept for provenance and backtesting.
CREATE TABLE IF NOT EXISTS market_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at  TEXT NOT NULL,
    source      TEXT NOT NULL,    -- 'poe.ninja' or 'manual'
    league      TEXT NOT NULL,
    category    TEXT NOT NULL,    -- e.g. 'Currency', 'Essence', 'Fossil'
    game_version TEXT,            -- game data version active at fetch time
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_market_snapshots ON market_snapshots(source, league, category, fetched_at);

CREATE TABLE IF NOT EXISTS prices (
    snapshot_id   INTEGER NOT NULL REFERENCES market_snapshots(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    variant       TEXT,
    chaos_value   REAL,
    divine_value  REAL,
    listing_count INTEGER,
    is_listing_price INTEGER NOT NULL DEFAULT 1  -- 1 = asking price, not a confirmed sale
);
CREATE INDEX IF NOT EXISTS ix_prices_name ON prices(name);

CREATE TABLE IF NOT EXISTS price_overrides (
    league     TEXT NOT NULL,
    name       TEXT NOT NULL,
    chaos_value REAL NOT NULL,
    note       TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league, name)
);

CREATE TABLE IF NOT EXISTS inventory (
    league     TEXT NOT NULL,
    name       TEXT NOT NULL,
    quantity   INTEGER NOT NULL,
    reserved   INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league, name)
);
