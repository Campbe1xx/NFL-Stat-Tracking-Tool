import pandas as pd
from nflprops import analytics as A, ingest
from nflprops.db import connect
from nflprops.qa import run_qa

GAMES = pd.DataFrame({"game_id": ["g1"], "season": [2026], "game_type": ["REG"], "week": [1], "gameday": ["2026-09-10"],
    "weekday": ["Thursday"], "gametime": ["20:20"], "away_team": ["AAA"], "away_score": [10], "home_team": ["BBB"], "home_score": [17],
    "overtime": [0], "spread_line": [3.5], "total_line": [44.5], "roof": ["dome"], "surface": ["turf"], "temp": [None], "wind": [None], "stadium": ["S"]})
PS = pd.DataFrame({"player_id": ["p1", "p2"], "player_display_name": ["Q One", "W Two"], "position": ["QB", "WR"], "team": ["BBB", "BBB"],
    "season": [2026] * 2, "week": [1] * 2, "season_type": ["REG"] * 2, "opponent_team": ["AAA"] * 2,
    "attempts": [30, 0], "completions": [20, 0], "passing_yards": [250, 0], "passing_tds": [1, 0], "passing_interceptions": [0, 0],
    "carries": [2, 0], "rushing_yards": [5, 0], "rushing_tds": [0, 0], "targets": [0, 8], "receptions": [0, 6],
    "receiving_yards": [0, 80], "receiving_tds": [0, 1]})

def test_pipeline(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    g = ingest.build_games(GAMES, 2026, "x", "2026-09-11")
    s = ingest.build_player_stats(PS, g, 2026, "y", "2026-09-11")
    ingest.upsert(con, g, s, "2026-09-11")
    ingest.upsert(con, g, s, "2026-09-11")  # idempotent
    assert con.execute("select count(*) from player_game_stats").fetchone()[0] == 2
    assert con.execute("select longest_rush from player_game_stats").fetchone()[0] is None  # NULL, not 0
    df = A.load(con)
    log, col = A.player_log(df, "p2", "Receiving Yards")
    assert A.over_under(log, col, 79.5)["over"] == 1
    assert "QA Report" in run_qa(con)
    assert A.opponent_allowed(df, pos_group="WR").loc["AAA", "receiving_yards"] == 80

def test_summarize_empty():
    assert A.summarize([None])["n"] == 0
