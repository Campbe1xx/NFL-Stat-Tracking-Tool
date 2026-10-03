# Data Dictionary

Raw tables hold only values taken from a cited source. Derived values are computed on read (`nflprops/analytics.py`) and never written back to raw tables.
**NULL = unavailable/not applicable. 0 = participated and recorded zero.** Missing values are never converted to 0; NULLs are excluded from averages/medians.

## games (raw)
| Field | Description | Type | Units | Example |
|---|---|---|---|---|
| game_id | Stable game identifier from the source (Game ID) | text | – | provider-specific |
| season, week | Season year; regular-season week | int | – | 2026, 1 |
| game_date, day, start_time | Kickoff date / weekday / time | text | ISO date | 2026-09-10 |
| home_team, away_team | Team abbreviations (team IDs) | text | – | KC |
| home_score, away_score | Final score | int | points | 27 |
| winning_team | Derived on ingest from scores if absent; `TIE` on equal score | text | – | |
| status | `scheduled` / `final` (only `final` games feed analytics) | text | – | final |
| overtime | 1 if overtime | int | flag | 0 |
| stadium, indoor_outdoor, surface, weather, precipitation | Venue/conditions (if available) | text | – | |
| temperature_f, wind_mph | Conditions | real | °F, mph | |
| closing_spread, closing_total, betting_source | **Betting-market information, not official statistics** | real/text | points | |
| source, source_url, retrieved_on, quality_status | Provenance (never fabricated) | text | – | |

## players (raw)
player_id (stable source ID; names are never used as keys), player_name, first_name, last_name, position, current_team, jersey_number.

## player_game_stats (raw; key = game_id + player_id)
| Field | Description | Type | Units |
|---|---|---|---|
| team | Team the player played for **in that game** | text | – |
| opponent, home_away | Derived on ingest from the game and `team` | text | – |
| position | Position for that game (defaults to players.position) | text | – |
| passing_attempts, completions, passing_yards, passing_touchdowns, interceptions | Passing | int | att/cmp/yards/TDs/INTs |
| passer_rating | Official rating if provided | real | – |
| longest_completion | Longest completion | int | yards |
| rushing_attempts, rushing_yards, rushing_touchdowns, longest_rush | Rushing (QB rushing included; yards may be negative) | int | att/yards/TDs/yards |
| targets, receptions, receiving_yards, receiving_touchdowns, longest_reception | Receiving | int | – |
| source, source_url, retrieved_on, quality_status | Provenance for the row | text | – |

## Logs
`data_quality_log` (conflicts, rejected rows, discrepancies; resolved flag) and `audit_log` (old/new value, time, reason for official corrections).

## Derived (calculated)
| Field | Calculation |
|---|---|
| games_played | count of final-game records for the player |
| `<stat>_total` | sum of non-NULL values |
| `<stat>_per_game` | total / number of games with non-NULL value |
| window (last3/last5/last8/season) | the last N chronological final-game records (by week, date); avg, median, min, max, population std dev (`statistics.pstdev`) over non-NULL values; `n` = sample size |
| home/away avg, vs-opponent avg | same summary restricted to those games |
| over_pct / under_pct | games with value > line (or < line) / games with non-NULL value. Pushes (== line) counted in neither. **Historical frequency, not a probability.** |
| opponent allowed | sum (and per-game) of stats by players whose `opponent` is the defense, over that defense's final games; window/home-away refer to the defense |
| position groups | QB→QB; RB, FB, HB→RB; WR→WR; TE→TE (position on the player-game row). Others excluded from position splits |
| combined historical hit | games in which every leg has data and every leg hit; count only, no product of rates |

Not yet modelled (need data feeds not included here): rest days, snap counts, injury designation, starter status.
