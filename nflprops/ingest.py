"""Weekly updater: pulls games + player-game stats from nflverse (derived from official NFL data).

Only regular-season (REG) games with final scores are loaded. Statistics the source does not
provide (longest rush/reception/completion, passer rating) are stored as NULL, never 0.
Existing records are never overwritten silently: changed values are written to change_log.
"""
import argparse, datetime as dt
import pandas as pd
from . import config
from .db import connect

PS_MAP = {"attempts": "passing_attempts", "completions": "completions", "passing_yards": "passing_yards",
          "passing_tds": "passing_touchdowns", "passing_interceptions": "interceptions",
          "carries": "rushing_attempts", "rushing_yards": "rushing_yards",
          "rushing_tds": "rushing_touchdowns", "targets": "targets", "receptions": "receptions",
          "receiving_yards": "receiving_yards", "receiving_tds": "receiving_touchdowns"}
STAT_COLS = ["passing_attempts", "completions", "passing_yards", "passing_touchdowns", "interceptions",
             "passer_rating", "longest_completion", "rushing_attempts", "rushing_yards", "rushing_touchdowns",
             "longest_rush", "targets", "receptions", "receiving_yards", "receiving_touchdowns",
             "longest_reception"]

def _n(v):
    return None if pd.isna(v) else v

def build_games(raw, season, url, now):
    g = raw[(raw.season == season) & (raw.game_type == "REG")]
    g = g[g.home_score.notna() & g.away_score.notna()]  # completed only
    out = pd.DataFrame({
        "game_id": g.game_id, "season": g.season, "week": g.week, "game_date": g.gameday,
        "day": g.get("weekday"), "start_time": g.get("gametime"), "home_team": g.home_team,
        "away_team": g.away_team, "home_score": g.home_score.astype(int), "away_score": g.away_score.astype(int),
        "overtime": g.get("overtime"), "stadium": g.get("stadium"), "roof": g.get("roof"),
        "surface": g.get("surface"), "temperature": g.get("temp"), "wind_mph": g.get("wind"),
        "betting_spread_close": g.get("spread_line"), "betting_total_close": g.get("total_line")})
    out["winning_team"] = [h if hs > a_ else (a if a_ > hs else "TIE") for h, a, hs, a_ in
                           zip(out.home_team, out.away_team, out.home_score, out.away_score)]
    out["game_status"] = "final"
    out["precipitation"] = None
    out["weather"] = None
    out["source"], out["source_url"], out["retrieved_at"] = config.SOURCE_NAME, url, now
    out["data_quality"] = "unverified_secondary"
    return out

def build_player_stats(ps, games, season, url, now):
    ps = ps[(ps.season == season) & (ps.season_type == "REG")].copy()
    ps = ps.rename(columns={k: v for k, v in PS_MAP.items() if k in ps.columns})
    ps = ps.loc[:, ~ps.columns.duplicated()]
    for c in STAT_COLS:
        if c not in ps.columns:
            ps[c] = pd.NA  # unavailable => NULL
    gl = pd.concat([games[["game_id", "week", "home_team", "away_team"]].assign(team=games.home_team, home_away="home"),
                    games[["game_id", "week", "home_team", "away_team"]].assign(team=games.away_team, home_away="away")])
    m = ps.merge(gl[["game_id", "week", "team", "home_away"]], on=["week", "team"], how="inner", validate="many_to_one")
    m["opponent"] = m.opponent_team if "opponent_team" in m else None
    m["source"], m["source_url"], m["retrieved_at"] = config.SOURCE_NAME, url, now
    m["data_quality"] = "unverified_secondary"
    return m

def upsert(con, games, stats, now):
    cur = con.cursor()
    gcols = list(games.columns)
    for r in games.itertuples(index=False):
        cur.execute(f"INSERT OR REPLACE INTO games({','.join(gcols)}) VALUES({','.join('?'*len(gcols))})",
                    [_n(x) for x in r])
    # players (stable GSIS id); current_team = latest team seen
    last = stats.sort_values("week").groupby("player_id").tail(1)
    for r in last.itertuples():
        name = getattr(r, "player_display_name", None) or getattr(r, "player_name", None)
        first, _, lastn = (name or "").partition(" ")
        pos = getattr(r, "position", None)
        cur.execute("INSERT OR REPLACE INTO players(player_id,player_name,first_name,last_name,position,current_team,jersey_number) "
                    "VALUES(?,?,?,?,?,?,NULL)", (r.player_id, name, first, lastn, _n(pos), r.team))
    cols = ["game_id", "player_id", "team", "opponent", "home_away"] + STAT_COLS + \
           ["source", "source_url", "retrieved_at", "data_quality"]
    for r in stats[cols].itertuples(index=False):
        rec = dict(zip(cols, [None if pd.isna(x) else (int(x) if isinstance(x, float) and x == int(x) and c in STAT_COLS and c != "passer_rating" else x)
                              for c, x in zip(cols, r)]))
        old = cur.execute("SELECT * FROM player_game_stats WHERE game_id=? AND player_id=? AND team=?",
                          (rec["game_id"], rec["player_id"], rec["team"])).fetchone()
        if old:
            oldd = dict(zip([d[0] for d in cur.description], old))
            for f in STAT_COLS:
                if oldd[f] != rec[f]:
                    cur.execute("INSERT INTO change_log VALUES(?,?,?,?,?,?,?,?)",
                                (now, rec["game_id"], rec["player_id"], rec["team"], f, oldd[f], rec[f],
                                 "source value changed on re-ingest (verify against official correction)"))
        cur.execute(f"INSERT OR REPLACE INTO player_game_stats({','.join(cols)}) VALUES({','.join('?'*len(cols))})",
                    list(rec.values()))
    con.commit()

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=config.SEASON)
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--games-src", default=config.GAMES_URL, help="URL or local CSV")
    ap.add_argument("--stats-src", default=None, help="URL or local CSV")
    a = ap.parse_args(argv)
    stats_src = a.stats_src or config.PLAYER_STATS_URL.format(season=a.season)
    now = dt.date.today().isoformat()
    games = build_games(pd.read_csv(a.games_src), a.season, a.games_src, now)
    ps_raw = pd.read_csv(stats_src)
    stats = build_player_stats(ps_raw, games, a.season, stats_src, now)
    con = connect(a.db)
    upsert(con, games, stats, now)
    print(f"Loaded {len(games)} completed games, {len(stats)} player-game rows into {a.db}")
    from .qa import run_qa
    print(run_qa(con, a.season))

if __name__ == "__main__":
    main()
