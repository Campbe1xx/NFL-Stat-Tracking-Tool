CREATE TABLE IF NOT EXISTS games (
  game_id TEXT PRIMARY KEY, season INTEGER NOT NULL, week INTEGER NOT NULL,
  game_date TEXT, day TEXT, start_time TEXT,
  home_team TEXT NOT NULL, away_team TEXT NOT NULL,
  home_score INTEGER, away_score INTEGER, winning_team TEXT,
  status TEXT NOT NULL DEFAULT 'scheduled', overtime INTEGER,
  stadium TEXT, indoor_outdoor TEXT, surface TEXT, weather TEXT,
  temperature_f REAL, wind_mph REAL, precipitation TEXT,
  -- betting-market information (NOT official statistics)
  closing_spread REAL, closing_total REAL, betting_source TEXT,
  source TEXT NOT NULL, source_url TEXT, retrieved_on TEXT,
  quality_status TEXT NOT NULL DEFAULT 'unverified'
);
CREATE TABLE IF NOT EXISTS players (
  player_id TEXT PRIMARY KEY, player_name TEXT NOT NULL,
  first_name TEXT, last_name TEXT, position TEXT, current_team TEXT, jersey_number INTEGER
);
-- NULL = unavailable / not applicable; 0 = participated and recorded zero.
CREATE TABLE IF NOT EXISTS player_game_stats (
  game_id TEXT NOT NULL REFERENCES games(game_id),
  player_id TEXT NOT NULL REFERENCES players(player_id),
  team TEXT NOT NULL, opponent TEXT NOT NULL, home_away TEXT NOT NULL CHECK (home_away IN ('home','away')),
  position TEXT,
  passing_attempts INTEGER, completions INTEGER, passing_yards INTEGER, passing_touchdowns INTEGER,
  interceptions INTEGER, passer_rating REAL, longest_completion INTEGER,
  rushing_attempts INTEGER, rushing_yards INTEGER, rushing_touchdowns INTEGER, longest_rush INTEGER,
  targets INTEGER, receptions INTEGER, receiving_yards INTEGER, receiving_touchdowns INTEGER, longest_reception INTEGER,
  source TEXT NOT NULL, source_url TEXT, retrieved_on TEXT,
  quality_status TEXT NOT NULL DEFAULT 'unverified',
  PRIMARY KEY (game_id, player_id)
);
CREATE TABLE IF NOT EXISTS data_quality_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, logged_at TEXT NOT NULL, game_id TEXT, player_id TEXT,
  field TEXT, severity TEXT NOT NULL, message TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, changed_at TEXT NOT NULL, table_name TEXT NOT NULL,
  key TEXT NOT NULL, field TEXT NOT NULL, old_value TEXT, new_value TEXT, reason TEXT
);
