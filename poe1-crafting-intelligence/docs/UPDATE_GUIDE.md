# Update guide: new patch or league

1. **Settings → Check for new game data.** The Overview tab warns when RePoE has a newer version.
2. Import it by running `scripts\setup.ps1` again (or `python -m poeci.knowledge.importer`). Old snapshots are kept.
3. Run the tests. A failing `realdata` test means the patch changed something the engine relied on. Investigate before using recommendations.
4. **If major.minor changed** (for example 3.30 → 3.31), the app marks rules as unverified. Then:
   - read the patch notes' crafting sections;
   - update `mechanics_registry.json` (statuses, notes, new mechanics, removals);
   - update `assumptions.json` if anything changed;
   - set `verified_for_patch` to the new patch and `last_reviewed` to today;
   - add an entry to `CHANGELOG.md`.
5. **Hotfixes** (same major.minor): import the data and run the tests. Read the hotfix notes for crafting changes.
