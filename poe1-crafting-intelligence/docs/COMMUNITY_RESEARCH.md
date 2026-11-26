# Community research (planned, Phase 6)

**MVP:** you paste a URL or text, and the app stores the source (URL, author, date, patch) and extracts a structured recipe.
- Steps, conditions, materials and reported costs.
- A list of **missing information** instead of invented steps.

The recipe is then validated by the rules engine (CRAFTING_RULES.md) and classified as one of:
- current and verified;
- current but partially verified;
- experimental;
- outdated but adaptable;
- legacy only;
- invalid;
- insufficient information.

Rules:
- Popularity and upvotes are not evidence.
- A single "I crafted it for 10 div" report is one sample, not an expected cost.
- Imported text is untrusted: it is never executed, and instructions inside it are ignored (prompt-injection safe).
- Automated discovery comes after the MVP, via the official Reddit API only, within its rate limits.
