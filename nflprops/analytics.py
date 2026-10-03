"""Derived statistics. All functions are pure reads of raw tables; nothing is stored back."""
import statistics

MARKETS = {
    "passing_yards": "Passing Yards", "passing_touchdowns": "Passing TDs", "interceptions": "Interceptions",
    "rushing_yards": "Rushing Yards", "rushing_touchdowns": "Rushing TDs", "longest_rush": "Longest Rush",
    "receptions": "Receptions", "receiving_yards": "Receiving Yards", "receiving_touchdowns": "Receiving TDs",
    "longest_reception": "Longest Reception", "targets": "Targets",
}
SEASON_TOTALS = ["passing_yards", "passing_touchdowns", "interceptions", "rushing_yards", "rushing_touchdowns",
                 "receptions", "targets", "receiving_yards", "receiving_touchdowns"]
WINDOWS = {"last3": 3, "last5": 5, "last8": 8, "season": None}
# Position groups used for opponent splits. Documented in docs/DATA_DICTIONARY.md.
POSITION_GROUPS = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "WR", "TE": "TE"}


def summarize(values):
    """Stats over non-NULL values. NULL (None) is excluded, never treated as 0."""
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0, "avg": None, "median": None, "min": None, "max": None, "stdev": None}
    return {"n": len(v), "avg": sum(v) / len(v), "median": statistics.median(v), "min": min(v), "max": max(v),
            "stdev": statistics.pstdev(v) if len(v) > 1 else None}


def check_market(market):
    if market not in MARKETS:
        raise ValueError(f"unknown market {market!r}")


def player_games(con, player_id, final_only=True):
    q = ("SELECT s.*, g.week, g.game_date, g.status FROM player_game_stats s JOIN games g USING(game_id) "
         "WHERE s.player_id=?" + (" AND g.status='final'" if final_only else "") + " ORDER BY g.week, g.game_date, s.game_id")
    return [dict(r) for r in con.execute(q, (player_id,))]


def windows(rows, market):
    """Rows must be chronological. Returns summary per window."""
    check_market(market)
    vals = [r[market] for r in rows]
    out = {}
    for name, n in WINDOWS.items():
        out[name] = summarize(vals if n is None else vals[-n:])
    return out


def split_summary(rows, market, key, value):
    return summarize([r[market] for r in rows if r[key] == value])


def hit_rate(rows, market, line):
    """Historical frequency over/under/push versus a line. Not a probability."""
    check_market(market)
    obs = [(r["game_id"], r["week"], r["opponent"], r[market]) for r in rows if r[market] is not None]
    over = [o for o in obs if o[3] > line]
    under = [o for o in obs if o[3] < line]
    n = len(obs)
    return {"line": line, "sample_size": n, "over": len(over), "under": len(under), "push": n - len(over) - len(under),
            "over_pct": len(over) / n if n else None, "under_pct": len(under) / n if n else None,
            "observations": [{"game_id": g, "week": w, "opponent": o, "value": v} for g, w, o, v in obs],
            "note": "Historical frequency only; not a predicted probability."}


def histogram(values, bins=10):
    v = [x for x in values if x is not None]
    if not v:
        return []
    lo, hi = min(v), max(v)
    if lo == hi:
        return [{"start": lo, "end": hi, "count": len(v)}]
    w = (hi - lo) / bins
    counts = [0] * bins
    for x in v:
        counts[min(int((x - lo) / w), bins - 1)] += 1
    return [{"start": lo + i * w, "end": lo + (i + 1) * w, "count": c} for i, c in enumerate(counts)]


def player_profile(con, player_id, market, line=None, opponent=None):
    check_market(market)
    p = con.execute("SELECT * FROM players WHERE player_id=?", (player_id,)).fetchone()
    if p is None:
        raise KeyError(player_id)
    rows = player_games(con, player_id)
    res = {"player": dict(p), "market": market, "games": rows, "windows": windows(rows, market),
           "home": split_summary(rows, market, "home_away", "home"), "away": split_summary(rows, market, "home_away", "away"),
           "histogram": histogram([r[market] for r in rows])}
    if opponent:
        res["vs_opponent"] = split_summary(rows, market, "opponent", opponent)
    if line is not None:
        res["hit_rate"] = hit_rate(rows, market, line)
    return res


def season_totals(con):
    out = []
    for p in con.execute("SELECT * FROM players ORDER BY player_name"):
        rows = player_games(con, p["player_id"])
        if not rows:
            continue
        rec = {"player_id": p["player_id"], "player_name": p["player_name"], "position": p["position"],
               "team": p["current_team"], "games_played": len(rows)}
        for m in SEASON_TOTALS:
            vals = [r[m] for r in rows if r[m] is not None]
            rec[m + "_total"] = sum(vals) if vals else None
            rec[m + "_per_game"] = sum(vals) / len(vals) if vals else None
        out.append(rec)
    return out


def rolling_table(con):
    out = []
    for p in con.execute("SELECT * FROM players ORDER BY player_name"):
        rows = player_games(con, p["player_id"])
        if not rows:
            continue
        for m in MARKETS:
            if all(r[m] is None for r in rows):
                continue
            for w, s in windows(rows, m).items():
                out.append({"player_id": p["player_id"], "player_name": p["player_name"], "market": m, "window": w,
                            **{k: s[k] for k in ("n", "avg", "median", "min", "max", "stdev")}})
    return out


def compare(con, player_ids, market, line=None):
    check_market(market)
    out = []
    for pid in player_ids:
        p = con.execute("SELECT player_name FROM players WHERE player_id=?", (pid,)).fetchone()
        if p is None:
            continue
        rows = player_games(con, pid)
        w = windows(rows, market)
        rec = {"player_id": pid, "player_name": p["player_name"], "games": w["season"]["n"], "season_avg": w["season"]["avg"],
               "last5_avg": w["last5"]["avg"], "median": w["season"]["median"], "stdev": w["season"]["stdev"]}
        if line is not None:
            hr = hit_rate(rows, market, line)
            rec["over_pct"], rec["sample_size"] = hr["over_pct"], hr["sample_size"]
        out.append(rec)
    return out  # intentionally unranked; the UI sorts on user's choice


def opponent_allowed(con, window=None, home_away=None, position_group=None):
    """Totals/averages allowed by each defense. home_away is the DEFENSE's venue."""
    allowed_cols = ["passing_yards", "passing_touchdowns", "interceptions", "rushing_yards", "rushing_touchdowns",
                    "receptions", "receiving_yards", "receiving_touchdowns"]
    teams = {}
    games = con.execute("SELECT * FROM games WHERE status='final' ORDER BY week, game_date, game_id").fetchall()
    by_def = {}
    for g in games:
        for d, venue in ((g["home_team"], "home"), (g["away_team"], "away")):
            by_def.setdefault(d, []).append((g["game_id"], venue))
    for d, glist in by_def.items():
        if home_away:
            glist = [x for x in glist if x[1] == home_away]
        if window:
            glist = glist[-window:]
        agg = {c: 0 for c in allowed_cols}
        for gid, _ in glist:
            for r in con.execute("SELECT * FROM player_game_stats WHERE game_id=? AND opponent=?", (gid, d)):
                if position_group and POSITION_GROUPS.get(r["position"]) != position_group:
                    continue
                for c in allowed_cols:
                    if r[c] is not None:
                        agg[c] += r[c]
        n = len(glist)
        teams[d] = {"games": n, **{c + "_total": agg[c] for c in allowed_cols},
                    **{c + "_per_game": (agg[c] / n if n else None) for c in allowed_cols}}
    return teams


# ---- Parlay -------------------------------------------------------------
def _side(leg):
    return leg.get("side", "over")


def correlation_flags(legs):
    """legs: dicts with player_id, market, line, side, team, game_id (resolved). Flags only; never removes legs."""
    flags = []
    fam = lambda m: "pass" if m.startswith("passing") else "rush" if m.startswith("rushing") else "rec"
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            a, b = legs[i], legs[j]
            tag = f"Leg {i + 1} & Leg {j + 1}"
            if a["player_id"] == b["player_id"]:
                flags.append({"legs": [i, j], "type": "same_player", "message": f"{tag}: same player (stats are strongly related, e.g. receptions and receiving yards)"})
                continue
            if a.get("game_id") and a.get("game_id") == b.get("game_id"):
                flags.append({"legs": [i, j], "type": "shared_game", "message": f"{tag}: both in game {a['game_id']}"})
            if a.get("team") and a.get("team") == b.get("team"):
                ma, mb = a["market"], b["market"]
                note = "same team"
                if {fam(ma), fam(mb)} == {"pass", "rec"}:
                    note = "same team passing/receiving production is typically linked"
                elif fam(ma) == fam(mb) == "rec" and _side(a) == _side(b):
                    note = "same-team receivers share a target pool and game script"
                flags.append({"legs": [i, j], "type": "same_team", "message": f"{tag}: {note}"})
            elif a.get("game_id") and a.get("game_id") == b.get("game_id"):
                flags.append({"legs": [i, j], "type": "opposing_team", "message": f"{tag}: opposing teams in the same game (game script may link them)"})
    return flags


def parlay(con, legs):
    out, resolved = [], []
    for leg in legs:
        check_market(leg["market"])
        rows = player_games(con, leg["player_id"])
        side = _side(leg)
        if side not in ("over", "under"):
            raise ValueError("side must be over or under")
        w = windows(rows, leg["market"])
        hr = hit_rate(rows, leg["market"], leg["line"])
        hit = (lambda v: v > leg["line"]) if side == "over" else (lambda v: v < leg["line"])
        hits = {o["game_id"] for o in hr["observations"] if hit(o["value"])}
        p = con.execute("SELECT player_name, current_team FROM players WHERE player_id=?", (leg["player_id"],)).fetchone()
        up = con.execute("SELECT g.game_id,g.home_team,g.away_team FROM games g WHERE g.status!='final' AND (g.home_team=? OR g.away_team=?) ORDER BY g.week LIMIT 1",
                         (p["current_team"], p["current_team"])).fetchone() if p else None
        info = {"player_id": leg["player_id"], "player": p["player_name"] if p else None, "market": leg["market"],
                "line": leg["line"], "side": side, "average": w["season"]["avg"], "median": w["season"]["median"],
                "recent_avg": w["last5"]["avg"], "over_pct": hr["over_pct"], "under_pct": hr["under_pct"],
                "sample_size": hr["sample_size"], "hit_game_ids": sorted(hits)}
        out.append(info)
        resolved.append({**leg, "side": side, "team": p["current_team"] if p else None,
                         "game_id": leg.get("game_id") or (up["game_id"] if up else None)})
    # Combined historical hit: only games in which ALL legs have an observation.
    sets = [{o["game_id"] for o in hit_rate(player_games(con, l["player_id"]), l["market"], l["line"])["observations"]} for l in legs]
    common = set.intersection(*sets) if sets else set()
    joint = None
    if len(legs) > 1 and common:
        joint = {"games_where_all_legs_have_data": len(common),
                 "games_where_all_legs_hit": len(common & set.intersection(*[set(i["hit_game_ids"]) for i in out]))}
    elif len(legs) > 1:
        joint = {"games_where_all_legs_have_data": 0, "games_where_all_legs_hit": 0,
                 "note": "No shared games in the sample; a combined historical hit rate cannot be computed from the data."}
    return {"legs": out, "n_legs": len(out), "combined_historical": joint, "correlation_flags": correlation_flags(resolved),
            "disclaimer": "Historical hit rate is the observed frequency in past games. It is NOT an estimated probability, "
                          "and individual rates are deliberately not multiplied together. Not a recommendation."}
