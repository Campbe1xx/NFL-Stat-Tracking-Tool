"""Completeness / validation checks and QA report."""
import datetime
from .db import now


def run_checks(con, expected_games_through_week=None):
    issues = []
    add = lambda sev, msg, **k: issues.append({"severity": sev, "message": msg, **k})
    finals = con.execute("SELECT * FROM games WHERE status='final'").fetchall()
    weeks = sorted({g["week"] for g in con.execute("SELECT week FROM games")})
    cov = {"games_total": con.execute("SELECT COUNT(*) FROM games").fetchone()[0], "games_final": len(finals),
           "player_game_records": con.execute("SELECT COUNT(*) FROM player_game_stats").fetchone()[0],
           "unique_players": con.execute("SELECT COUNT(DISTINCT player_id) FROM player_game_stats").fetchone()[0],
           "weeks": weeks}
    # games
    dup = con.execute("SELECT season,week,home_team,away_team,COUNT(*) c FROM games GROUP BY 1,2,3,4 HAVING c>1").fetchall()
    for d in dup:
        add("error", f"duplicate game {tuple(d)[:4]}")
    for g in finals:
        if g["home_score"] is None or g["away_score"] is None:
            add("error", "final game missing score", game_id=g["game_id"])
        if not g["source"]:
            add("error", "game missing source", game_id=g["game_id"])
    if expected_games_through_week is not None:
        got = {g["game_id"] for g in finals}
        cov["expected_games"] = expected_games_through_week
        if len(got) != expected_games_through_week:
            add("error", f"{len(got)} final games present but {expected_games_through_week} expected: missing games must be loaded")
    # players
    for r in con.execute("SELECT s.game_id,s.player_id FROM player_game_stats s LEFT JOIN players p USING(player_id) WHERE p.player_id IS NULL"):
        add("error", "stat row with unknown player_id", game_id=r[0], player_id=r[1])
    for r in con.execute("SELECT player_name,COUNT(*) c FROM players GROUP BY player_name HAVING c>1"):
        add("info", f"{r[0]}: {r[1]} distinct players share this name (kept apart by player_id)")
    # statistics
    for r in con.execute("SELECT s.*, g.status, g.home_team, g.away_team FROM player_game_stats s JOIN games g USING(game_id)"):
        gid, pid = r["game_id"], r["player_id"]
        if r["team"] not in (r["home_team"], r["away_team"]):
            add("error", "player team did not play in game", game_id=gid, player_id=pid)
        for k in ("passing_attempts", "completions", "passing_yards", "passing_touchdowns", "interceptions", "rushing_attempts",
                  "rushing_touchdowns", "targets", "receptions", "receiving_touchdowns"):
            if r[k] is not None and r[k] < 0:
                add("error", f"negative {k}", game_id=gid, player_id=pid)
        if (r["completions"] is not None and r["passing_attempts"] is not None and r["completions"] > r["passing_attempts"]):
            add("error", "completions exceed attempts", game_id=gid, player_id=pid)
        if r["receptions"] is not None and r["targets"] is not None and r["receptions"] > r["targets"]:
            add("error", "receptions exceed targets", game_id=gid, player_id=pid)
        if r["receiving_yards"] and not r["receptions"]:
            add("warning", "receiving yards without receptions", game_id=gid, player_id=pid)
        if r["passing_touchdowns"] and not r["passing_attempts"]:
            add("warning", "passing TDs without attempts", game_id=gid, player_id=pid)
        if r["rushing_touchdowns"] and not r["rushing_attempts"]:
            add("warning", "rushing TDs without attempts", game_id=gid, player_id=pid)
        if r["longest_rush"] is not None and r["rushing_yards"] is not None and r["rushing_attempts"] and r["longest_rush"] > max(r["rushing_yards"], 0) + 200:
            add("warning", "longest_rush implausible vs total", game_id=gid, player_id=pid)
        if not r["source"]:
            add("error", "stat row missing source", game_id=gid, player_id=pid)
    # reconciliation: team totals from players must match across passing/receiving (completions-yards)
    for g in finals:
        for team in (g["home_team"], g["away_team"]):
            t = con.execute("SELECT SUM(passing_yards) py, SUM(passing_touchdowns) ptd, COUNT(passing_yards) npy FROM player_game_stats WHERE game_id=? AND team=?", (g["game_id"], team)).fetchone()
            o = con.execute("SELECT SUM(receiving_yards) ry, SUM(receiving_touchdowns) rtd, COUNT(receiving_yards) nry FROM player_game_stats WHERE game_id=? AND team=?", (g["game_id"], team)).fetchone()
            # Passing yards (gross) vs receiving yards must reconcile on the same team; sacks do not affect either.
            if t["npy"] and o["nry"] and t["py"] != o["ry"]:
                add("warning", f"{team}: passing yards {t['py']} != receiving yards {o['ry']} (check missing/duplicated players)", game_id=g["game_id"])
            if t["npy"] and o["nry"] and (t["ptd"] or 0) != (o["rtd"] or 0):
                add("warning", f"{team}: passing TDs {t['ptd']} != receiving TDs {o['rtd']}", game_id=g["game_id"])
        if g["status"] == "final" and con.execute("SELECT COUNT(*) FROM player_game_stats WHERE game_id=?", (g["game_id"],)).fetchone()[0] == 0:
            add("warning", "final game has no player records", game_id=g["game_id"])
    nulls = {}
    for col in ("passing_yards", "rushing_yards", "receiving_yards", "longest_rush", "longest_reception", "targets"):
        nulls[col] = con.execute(f"SELECT COUNT(*) FROM player_game_stats WHERE {col} IS NULL").fetchone()[0]
    cov["null_counts"] = nulls
    cov["open_conflicts"] = con.execute("SELECT COUNT(*) FROM data_quality_log WHERE resolved=0 AND severity IN ('conflict','rejected')").fetchone()[0]
    cov["source_coverage"] = {r[0]: r[1] for r in con.execute("SELECT source,COUNT(*) FROM player_game_stats GROUP BY source")}
    return {"coverage": cov, "issues": issues, "passed": not any(i["severity"] == "error" for i in issues)}


def render_report(result):
    c = result["coverage"]
    L = ["# QA Report", "", f"Generated: {now()}", "", "## Dataset coverage"]
    for k in ("games_total", "games_final", "player_game_records", "unique_players", "weeks"):
        L.append(f"- {k}: {c[k]}")
    if "expected_games" in c:
        L.append(f"- expected_games: {c['expected_games']}")
    L += ["", "## Data quality", f"- open conflicts/rejections: {c['open_conflicts']}",
          f"- NULL counts: {c['null_counts']}", f"- source coverage: {c['source_coverage']}", "",
          f"## Validation: {'PASSED' if result['passed'] else 'FAILED'}", f"{len(result['issues'])} issue(s) listed below."]
    if not result["issues"]:
        L.append("- none")
    for i in result["issues"]:
        L.append(f"- [{i['severity']}] {i['message']} {i.get('game_id') or ''} {i.get('player_id') or ''}".rstrip())
    L += ["", "Unresolved issues above must be reviewed against the official NFL gamebook before use."]
    return "\n".join(L) + "\n"
