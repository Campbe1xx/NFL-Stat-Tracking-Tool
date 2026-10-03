SEASON = 2026
DB_PATH = "data/nfl.db"
SOURCE_NAME = "nflverse"
GAMES_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
PLAYER_STATS_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
                    "player_stats/player_stats_{season}.csv")

# Position classification used for opponent-vs-position splits.
POSITION_GROUPS = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB",
                   "WR": "WR", "TE": "TE"}

# market label -> (column, unit)
MARKETS = {
    "Passing Yards": "passing_yards",
    "Passing TDs": "passing_touchdowns",
    "Interceptions": "interceptions",
    "Rushing Yards": "rushing_yards",
    "Rushing TDs": "rushing_touchdowns",
    "Longest Rush": "longest_rush",
    "Receptions": "receptions",
    "Receiving Yards": "receiving_yards",
    "Receiving TDs": "receiving_touchdowns",
    "Longest Reception": "longest_reception",
}
