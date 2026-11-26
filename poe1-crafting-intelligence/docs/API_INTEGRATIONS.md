# API integrations

## poe.ninja (implemented, unverified live)

`backend/poeci/market/poeninja.py`

- Endpoints: `/api/data/currencyoverview?league=<L>&type=Currency|Fragment` and `/api/data/itemoverview?league=<L>&type=Essence|Fossil|Resonator|Beast|Oil|DeliriumOrb|BaseType|ClusterJewel|Unique*`.
- Fields read:
  - currency overview: `currencyTypeName`, `chaosEquivalent`, `receive.listing_count`;
  - item overview: `name`, `chaosValue`, `divineValue`, `listingCount`, `variant`, `levelRequired`.
- Politeness:
  - one request at a time (process lock);
  - at most one fetch per (league, category) per `POECI_MARKET_CACHE_SECONDS` (default 900);
  - HTTP 429 handling;
  - an honest User-Agent with no personal data.
- Schema drift: unexpected shapes raise `MarketError` and are shown in the UI; cached data stays usable.
- **First-run check on your PC:** Settings → Fetch prices. If a category errors, copy the error text into an issue or chat so the adapter can be adjusted. poe.ninja docs say "breaking changes can happen without notice".
- Scarab categories were removed from the adapter because Scarabs were removed in 3.30.

## RePoE (implemented, verified)

`backend/poeci/knowledge/importer.py`: `version.txt` plus 8 JSON files. The importer rejects invalid JSON and writes to a `.partial` folder first, so an interrupted download never corrupts the current snapshot.

## Planned

- **GGG OAuth:** read-only scopes `account:stashes` and `account:characters` for your own inventory. This needs an app registration approved by GGG. Without it, inventory is entered manually.
- **Reddit:** personal script app for reading posts and comments from submitted URLs.
- **Trade links:** generated URLs that open the official trade site in your browser with a pre-filled query.
