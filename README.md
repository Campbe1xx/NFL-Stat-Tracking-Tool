# NFL Stat Tracking Tool — 2026 Regular Season Player Prop Analytics

A dependency-free (Python 3.9+ stdlib) game-by-game player database (SQLite), validation/QA, derived stats, export, and a local interactive dashboard.

**No NFL data is bundled.** This tool never invents or estimates statistics. Official 2026 data must be loaded from an authoritative source (NFL.com stats/gamebooks, etc.) with its source reference; the app does not scrape anything.

## Weekly workflow
1. Put `games`, `players`, `player_game_stats` as `.csv` or `.json` in a directory (columns: see `nflprops/schema.sql`; `source` required, include `source_url`, `retrieved_on`, `quality_status`; leave unknown values empty → NULL).
2. `python -m nflprops ingest data/incoming` — validates, inserts new records, never overwrites a differing value (conflict is written to `data_quality_log`). Use `--correction --reason "NFL stat correction ..."` for official corrections; old values go to `audit_log`.
3. `python -m nflprops qa --expected-games N --output docs/QA_REPORT.md` — completeness, duplicates, impossible values, team-total reconciliation (passing vs. receiving yards/TDs).
4. `python -m nflprops serve` → http://127.0.0.1:8000 (Player Explorer, Prop Analyzer, Parlay Builder, Comparison, Opponents, Export/QA). Derived stats are recomputed on every request.
5. `python -m nflprops export data/export` — CSV per table, JSON, Excel.

Cross-source verification and discrepancy resolution against the official gamebook remain a manual step: record outcomes in `data_quality_log` / `quality_status`. See `docs/DATA_DICTIONARY.md`. Tests: `python -m unittest discover -s tests` (synthetic fixtures only).

Output is historical frequency, not probability or betting advice.
