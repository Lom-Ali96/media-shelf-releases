-- Crafts the user saved from the Route Planner, with their own sale price (ROI board).
CREATE TABLE IF NOT EXISTS saved_plans (
    league          TEXT NOT NULL,
    key             TEXT NOT NULL,   -- hash of base, item level, influences, wanted mods
    base            TEXT NOT NULL,
    item_level      INTEGER NOT NULL,
    influences      TEXT NOT NULL,   -- JSON list
    wants           TEXT NOT NULL,   -- JSON list of {mod_type, max_tier, bench}
    sale_chaos      REAL NOT NULL,   -- entered by the user (checked on the trade site)
    best_route      TEXT,
    best_cost_chaos REAL,            -- expected cost of the cheapest route when saved
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (league, key)
);
