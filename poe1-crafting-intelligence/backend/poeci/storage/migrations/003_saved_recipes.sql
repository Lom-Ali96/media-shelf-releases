-- Crafting routes saved from Reddit posts, guides or your own notes (Recipes tab).
CREATE TABLE IF NOT EXISTS saved_recipes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    source_url  TEXT,
    source_text TEXT,              -- the pasted post, kept so the steps can be re-checked
    base        TEXT NOT NULL,
    item_level  INTEGER NOT NULL,
    influences  TEXT NOT NULL,     -- JSON list
    wants       TEXT NOT NULL,     -- JSON list of {mod_type, max_tier}
    steps       TEXT NOT NULL,     -- JSON list of steps (see engine/recipe.py: recipe_from_json)
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_saved_recipes_base ON saved_recipes(base);

-- Craft ideas collected from Path of Building imports or pasted (trade) items, with the price seen.
CREATE TABLE IF NOT EXISTS saved_ideas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    league      TEXT NOT NULL,
    name        TEXT NOT NULL,
    base        TEXT NOT NULL,
    item_level  INTEGER NOT NULL,
    influences  TEXT NOT NULL,     -- JSON list
    wants       TEXT NOT NULL,     -- JSON list of {mod_type, max_tier, bench}
    price_chaos REAL,              -- listing/sale price you saw (optional)
    source      TEXT NOT NULL,     -- 'pob', 'pasted' or 'manual'
    best_route  TEXT,
    best_cost_chaos REAL,
    created_at  TEXT NOT NULL
);
