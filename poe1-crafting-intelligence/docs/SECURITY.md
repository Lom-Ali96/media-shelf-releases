# Security and compliance

- **No game automation.** No input simulation, memory reading, client modification, trading, whispering or currency use. The app only analyses.
- **No passwords and no session cookies.** Future account access uses GGG's official OAuth with read-only scopes only.
- **Local by default.** The server binds to 127.0.0.1. Exposing it with `POECI_HOST=0.0.0.0` makes it reachable on your network *without authentication*. Only do that on a trusted home network.
- **External requests:**
  - only to the documented sources in DATA_SOURCES.md;
  - cached and rate-limited;
  - with a User-Agent that contains no personal data.
- **Untrusted content.** Pasted items and imported posts are treated as data. The UI escapes all text before display.
- **Secrets.** Future API keys go in environment variables or the OS keyring, never in Git.
