# Market analysis

Implemented:
- poe.ninja prices per league and category, cached and stored with their raw payload.
- Manual overrides, which take priority.
- Price lookup used by the simulator for expected cost.

Rules that every later feature must keep:
- poe.ninja values are **listing-based asking prices**, not confirmed sales. Rows are stored with `is_listing_price = 1`.
- Every price carries its source and `as_of` time. The UI must show data age, and stale data must lower confidence.
- Rare-item valuation will give **conservative / expected / optimistic** values with a confidence score. When comparables are scarce, it says so.
- Owned materials are valued at opportunity cost (what they would sell for), not as free.
