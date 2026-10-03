# NFL Stat Tracking Tool – 2026 Regular-Season Player Prop Analytics

SQLite database + Streamlit dashboard of game-by-game player stats (Game → Team → Player → Performance).
Descriptive history only: no predictions, no betting recommendations, no invented numbers.

## Usage
```
pip install -r requirements.txt
python -m nflprops.ingest            # weekly: loads newly completed REG games, writes QA to stdout
streamlit run app.py
pytest
```
`ingest` is idempotent. Re-ingesting a changed value is recorded in `change_log` (old/new) instead of silently overwriting. QA anomalies go to `data_quality_log`.
Use `--games-src/--stats-src` for local CSVs. Raw tables (`games`, `players`, `player_game_stats`) hold only source data; all derived metrics are computed on read in `nflprops/analytics.py`.

## Important limitations (honest status)
- **No 2026 data is bundled.** Run the ingest after games are played; the sandbox that built this had no data.
- Source is nflverse (secondary, derived from NFL data). Every row is tagged `data_quality = unverified_secondary`; cross-checking with official gamebooks is **not automated** and must be done manually for discrepancies (record them in `data_quality_log`/`change_log`).
- Longest rush/reception/completion and passer rating are not in the source → stored as **NULL** (never 0); the longest-* markets will be empty until a gamebook source is added.
- Weather/precipitation, rest days, snaps, injury designation, starter status are not loaded. Spread/total are **betting-market data, not official stats** (`betting_*` columns).
- Parlay "historical hit rate" counts only games where all legs' players have records, and is not a probability.

## Position classification (opponent splits)
QB=QB; RB=RB, FB, HB; WR=WR; TE=TE (`config.POSITION_GROUPS`). Defense "allowed" = stats by opposing offensive players.

## Data dictionary
See [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).
