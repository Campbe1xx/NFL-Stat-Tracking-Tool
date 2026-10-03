"""All derived metrics. Raw tables are never modified; everything here is calculated on read."""
import numpy as np, pandas as pd
from . import config

def load(con):
    q = """SELECT s.*, p.player_name, p.position, g.week, g.game_date, g.betting_spread_close,
                  g.betting_total_close, g.temperature, g.wind_mph, g.roof
           FROM player_game_stats s JOIN players p USING(player_id) JOIN games g USING(game_id)
           ORDER BY g.game_date"""
    return pd.read_sql(q, con)

def summarize(values):
    v = pd.Series(values, dtype="float").dropna()
    if v.empty:
        return dict(n=0, average=None, median=None, minimum=None, maximum=None, std_dev=None)
    return dict(n=len(v), average=v.mean(), median=v.median(), minimum=v.min(), maximum=v.max(),
                std_dev=v.std(ddof=1) if len(v) > 1 else None)

def player_log(df, player_id, market):
    col = config.MARKETS.get(market, market)
    return df[df.player_id == player_id].sort_values("game_date").reset_index(drop=True), col

def windows(log, col, sizes=(3, 5, 8)):
    out = {"Season": summarize(log[col])}
    for k in sizes:
        out[f"Last {k}"] = summarize(log[col].tail(k))
    return pd.DataFrame(out).T

def over_under(log, col, line):
    v = log[col].dropna()
    n = len(v)
    over, under, push = int((v > line).sum()), int((v < line).sum()), int((v == line).sum())
    return dict(sample_size=n, over=over, under=under, push=push,
                over_pct=over / n if n else None, under_pct=under / n if n else None)

def splits(log, col, opponent=None):
    r = {"Home": summarize(log[log.home_away == "home"][col]), "Away": summarize(log[log.home_away == "away"][col])}
    if opponent:
        r[f"vs {opponent}"] = summarize(log[log.opponent == opponent][col])
    return pd.DataFrame(r).T

def season_totals(df):
    g = df.groupby(["player_id", "player_name", "position"], dropna=False)
    cols = ["passing_yards", "passing_touchdowns", "interceptions", "rushing_yards", "rushing_touchdowns",
            "receptions", "targets", "receiving_yards", "receiving_touchdowns"]
    t = g[cols].sum(min_count=1)  # all-NULL stays NULL
    t["games_played"] = g.game_id.nunique()
    for c in cols:
        t[c + "_per_game"] = t[c] / t.games_played
    return t.reset_index()

def classify(pos):
    return config.POSITION_GROUPS.get(pos)

def opponent_allowed(df, window=None, home_away=None, pos_group=None):
    """Yards/TDs/etc. allowed by each defense (= stats by opposing offensive players), per game."""
    d = df.copy()
    d["pos_group"] = d.position.map(classify)
    if pos_group:
        d = d[d.pos_group == pos_group]
    if home_away:  # defense's venue is the opposite of the offensive player's
        d = d[d.home_away == ("away" if home_away == "home" else "home")]
    cols = ["passing_yards", "passing_touchdowns", "interceptions", "rushing_yards", "rushing_touchdowns",
            "receptions", "receiving_yards", "receiving_touchdowns"]
    per_game = d.groupby(["opponent", "game_id", "week"])[cols].sum(min_count=1).reset_index()
    if window:
        per_game = per_game.sort_values("week").groupby("opponent").tail(window)
    r = per_game.groupby("opponent")[cols].mean()
    r["games"] = per_game.groupby("opponent").game_id.nunique()
    return r

def histogram(values, bins=10):
    v = pd.Series(values, dtype="float").dropna()
    return np.histogram(v, bins=bins) if len(v) else (np.array([]), np.array([]))

def leg_info(df, leg):
    """leg: dict(player_id, market, line, side). Adds team / game info for correlation checks."""
    log, col = player_log(df, leg["player_id"], leg["market"])
    ou = over_under(log, col, leg["line"])
    s = summarize(log[col])
    team = log.team.iloc[-1] if len(log) else None
    return dict(**leg, column=col, team=team, average=s["average"], median=s["median"],
                recent_avg=summarize(log[col].tail(5))["average"], **ou)

def joint_history(df, legs):
    """Games in which ALL legs' players have a record; fraction where every leg hit.
    Historical frequency only, not a probability. Legs of the same player need separate games."""
    frames = []
    for i, l in enumerate(legs):
        col = config.MARKETS[l["market"]]
        x = df[df.player_id == l["player_id"]][["game_id", col]].dropna()
        hit = x[col] > l["line"] if l["side"] == "Over" else x[col] < l["line"]
        frames.append(pd.DataFrame({"game_id": x.game_id, f"leg{i}": hit}).drop_duplicates("game_id"))
    if not frames:
        return dict(shared_games=0, all_hit=0, rate=None)
    m = frames[0]
    for f in frames[1:]:
        m = m.merge(f, on="game_id")
    n = len(m)
    allhit = int(m.drop(columns="game_id").all(axis=1).sum()) if n else 0
    return dict(shared_games=n, all_hit=allhit, rate=allhit / n if n else None)

def correlation_flags(infos, game_by_team):
    """Informational flags only; nothing is removed or recommended."""
    flags = []
    for i in range(len(infos)):
        for j in range(i + 1, len(infos)):
            a, b = infos[i], infos[j]
            rel = []
            if a["player_id"] == b["player_id"]:
                rel.append("Same player")
            if a["team"] and a["team"] == b["team"]:
                rel.append("Same team")
            elif game_by_team.get(a["team"]) and game_by_team.get(a["team"]) == game_by_team.get(b["team"]):
                rel.append("Opposing teams (shared game)")
            if not rel:
                continue
            note = ""
            ps = {"Passing Yards", "Passing TDs"}
            rs = {"Receiving Yards", "Receiving TDs", "Receptions"}
            if "Same team" in rel and ((a["market"] in ps and b["market"] in rs) or (b["market"] in ps and a["market"] in rs)):
                note = "Passing and receiving outcomes for the same offense tend to move together."
            elif "Same player" in rel and {a["market"], b["market"]} == {"Receptions", "Receiving Yards"}:
                note = "Receptions and receiving yards for one player are mechanically related."
            elif "Same team" in rel and a["market"] == b["market"] and a["market"] in rs:
                note = "Teammates compete for the same targets/passing volume."
            elif "Opposing teams (shared game)" in rel:
                note = "Opposing players share game script (score, pace)."
            flags.append(dict(leg_a=i + 1, leg_b=j + 1, relationship=", ".join(rel), note=note))
    return flags
