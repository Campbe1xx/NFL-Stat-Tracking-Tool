import sqlite3, os

SCHEMA = """
CREATE TABLE IF NOT EXISTS games(
 game_id TEXT PRIMARY KEY, season INT, week INT, game_date TEXT, day TEXT, start_time TEXT,
 home_team TEXT, away_team TEXT, home_score INT, away_score INT, winning_team TEXT,
 game_status TEXT, overtime INT, stadium TEXT, roof TEXT, surface TEXT, temperature REAL,
 wind_mph REAL, precipitation TEXT, weather TEXT,
 betting_spread_close REAL, betting_total_close REAL,   -- market data, NOT official stats
 source TEXT, source_url TEXT, retrieved_at TEXT, data_quality TEXT);
CREATE TABLE IF NOT EXISTS players(
 player_id TEXT PRIMARY KEY, player_name TEXT, first_name TEXT, last_name TEXT,
 position TEXT, current_team TEXT, jersey_number TEXT);
CREATE TABLE IF NOT EXISTS player_game_stats(
 game_id TEXT, player_id TEXT, team TEXT, opponent TEXT, home_away TEXT,
 passing_attempts INT, completions INT, passing_yards INT, passing_touchdowns INT, interceptions INT,
 passer_rating REAL, longest_completion INT,
 rushing_attempts INT, rushing_yards INT, rushing_touchdowns INT, longest_rush INT,
 targets INT, receptions INT, receiving_yards INT, receiving_touchdowns INT, longest_reception INT,
 source TEXT, source_url TEXT, retrieved_at TEXT, data_quality TEXT,
 PRIMARY KEY(game_id, player_id, team));
CREATE TABLE IF NOT EXISTS change_log(
 changed_at TEXT, game_id TEXT, player_id TEXT, team TEXT, field TEXT, old_value TEXT, new_value TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS data_quality_log(
 logged_at TEXT, game_id TEXT, player_id TEXT, check_name TEXT, detail TEXT);
"""

def connect(path):
    d = os.path.dirname(path)
    if d: os.makedirs(d, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con
