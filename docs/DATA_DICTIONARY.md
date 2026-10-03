# Data Dictionary
Source for raw fields: nflverse (`source`, `source_url`, `retrieved_at` stored per row). NULL = unavailable; 0 = participated, recorded zero.

## games (raw)
| Field | Description | Type | Units |
|---|---|---|---|
| game_id | Source game identifier | text | – |
| season, week | Season year / week number | int | – |
| game_date, day, start_time | Kickoff date, weekday, time | text | ISO date |
| home_team, away_team | Team abbreviations | text | – |
| home_score, away_score | Final scores | int | points |
| winning_team | Calculated: higher score, or TIE | text | – |
| game_status | `final` (only completed games loaded) | text | – |
| overtime | Overtime indicator | int | 0/1 |
| stadium, roof, surface | Venue info (roof = indoor/outdoor) | text | – |
| temperature, wind_mph | Weather where provided | real | °F, mph |
| precipitation, weather | Not loaded (NULL) | text | – |
| betting_spread_close, betting_total_close | **Market data, not official stats** | real | points |
| source, source_url, retrieved_at, data_quality | Provenance | text | – |

## players (raw)
player_id (stable GSIS id), player_name, first_name, last_name, position, current_team (latest team seen), jersey_number (NULL, not loaded).

## player_game_stats (raw; key = game_id, player_id, team)
| Field | Description | Units |
|---|---|---|
| team, opponent, home_away | Team the stat was recorded for; opponent; `home`/`away` | – |
| passing_attempts, completions | Pass attempts / completions | count |
| passing_yards, passing_touchdowns, interceptions | Passing results | yards / TDs / INTs thrown |
| passer_rating, longest_completion | Currently NULL (not in source) | – / yards |
| rushing_attempts, rushing_yards, rushing_touchdowns | Rushing incl. QBs | count / yards / TDs |
| longest_rush | Currently NULL (not in source) | yards |
| targets, receptions, receiving_yards, receiving_touchdowns | Receiving | count / yards / TDs |
| longest_reception | Currently NULL (not in source) | yards |
| source, source_url, retrieved_at, data_quality | Provenance | – |

## Audit tables
`change_log(changed_at, game_id, player_id, team, field, old_value, new_value, reason)`; `data_quality_log(logged_at, game_id, player_id, check_name, detail)`.

## Calculated (never stored in raw tables; `nflprops/analytics.py`)
| Field | Calculation |
|---|---|
| games_played | distinct games with a record |
| season totals | sum of the raw column (all-NULL stays NULL) |
| *_per_game | total / games_played |
| window (Season, Last 3/5/8) | average, median, min, max, sample std dev (n-1) over the player's most recent N games with non-NULL values |
| over/under | Over: stat > line; Under: stat < line; Push: equal. pct = count / non-NULL sample size |
| home/away/opponent split | summary over games filtered by `home_away` / `opponent` |
| opponent allowed | per game, sum of opposing players' stats (optionally by position group, venue, last N); then averaged over games |
| joint historical hit rate | among games where every leg's player has a record, share where all legs hit; a frequency, not a probability |
