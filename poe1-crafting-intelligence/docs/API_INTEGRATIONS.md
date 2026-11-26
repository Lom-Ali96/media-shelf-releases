# API integrations

## poe.ninja (implemented, verified live 2026-11-26)

`backend/poeci/market/poeninja.py`

- The old `/api/data/currencyoverview` and `/api/data/itemoverview` endpoints now return 404.
- Endpoints (as used by poe.ninja's own site on 2026-11-26):
  - `/poe1/api/economy/exchange/current/overview?league=<L>&type=Currency|Fragment|Essence|Fossil|Resonator|Oil|DeliriumOrb`;
  - `/poe1/api/economy/stash/current/item/overview?league=<L>&type=Beast|BaseType|ClusterJewel|Unique*`.
- League names are poe.ninja's short names, e.g. `Covens` (not "Covens of Umbra"); the list is at `/poe1/api/data/index-state` → `economyLeagues[].name`. An unknown league returns HTTP 200 with empty lists, so an empty result is reported as an error.
- Fields read:
  - exchange: `core.primary` (must be `chaos`), `core.rates.divine`, `lines[].id` + `primaryValue`, names from `items[].id` → `name`. No listing count is given (only trade volume), so `listing_count` is empty;
  - stash item: `name`, `chaosValue`, `divineValue`, `listingCount`, `variant`, `levelRequired`.
- Politeness:
  - one request at a time (process lock);
  - at most one fetch per (league, category) per `POECI_MARKET_CACHE_SECONDS` (default 900);
  - HTTP 429 handling;
  - an honest User-Agent with no personal data.
- Schema drift: unexpected shapes raise `MarketError` and are shown in the UI; cached data stays usable.
- **First-run check on your PC:** Settings → Fetch prices. If a category errors, copy the error text into an issue or chat so the adapter can be adjusted. poe.ninja docs say "breaking changes can happen without notice".
- Scarab categories were removed from the adapter because Scarabs were removed in 3.30.

## Official trade site (links only)

`backend/poeci/market/trade.py`

- The app **never** runs trade searches, reads listings or prices, or logs in. It only builds a URL `https://www.pathofexile.com/trade/search/<league>?q=<query JSON>` that you open in your own browser.
- To pre-fill mod filters it downloads the public static stat list `/api/trade/data/stats` (≈2 MB) once and caches it in `data/trade_stats.json`; it downloads it again only when the imported game data version changes. Approved by the user on 2026-11-26.
- Mapping: the mod text of the *worst accepted tier* with numbers replaced by `#` is matched to the `explicit` group; mods with a `local_` stat prefer the `(Local)` entry; "reduced" is matched as "increased" with a negative maximum. Single-value lines get a minimum; "Adds # to #" lines get none (how the site combines the two values is unverified). Bench mods and mods that can't roll on the base are left out, with a note.
- Trade league ids match poe.ninja's names (`Covens`, checked 2026-11-26).
- Verified by the user on 2026-11-26: the `?q=` link opens with base, rarity and stat filters applied (Covens). If you are not logged in, the login redirect drops the filters: log in first, then click the button again.

## RePoE (implemented, verified)

`backend/poeci/knowledge/importer.py`: `version.txt` plus 8 JSON files. The importer rejects invalid JSON and writes to a `.partial` folder first, so an interrupted download never corrupts the current snapshot.

## Planned

- **GGG OAuth:** read-only scopes `account:stashes` and `account:characters` for your own inventory. This needs an app registration approved by GGG. Without it, inventory is entered manually.
- **Reddit:** personal script app for reading posts and comments from submitted URLs.
- **Trade links:** generated URLs that open the official trade site in your browser with a pre-filled query.
