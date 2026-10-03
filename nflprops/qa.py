import datetime as dt
import pandas as pd

def run_qa(con, season=2026):
    q = lambda s: pd.read_sql(s, con)
    games = q("SELECT * FROM games"); st = q("SELECT * FROM player_game_stats"); pl = q("SELECT * FROM players")
    L = [f"# QA Report - {season} regular season (generated {dt.date.today()})", "", "## Coverage"]
    L += [f"- Completed games loaded: {len(games)}", f"- Player-game records: {len(st)}",
          f"- Unique players: {pl.player_id.nunique()}",
          f"- Weeks included: {sorted(games.week.unique().tolist())}",
          f"- Duplicate game_ids: {int(games.game_id.duplicated().sum())}",
          f"- Duplicate player/game/team records: {int(st.duplicated(['game_id','player_id','team']).sum())}",
          f"- Duplicate player_ids: {int(pl.player_id.duplicated().sum())}",
          f"- Missing player_ids in stats: {int(st.player_id.isna().sum())}",
          f"- Stat rows with no matching player: {int((~st.player_id.isin(pl.player_id)).sum())}"]
    if len(games):
        exp = games.groupby("week").size()
        L.append("- Games per week: " + ", ".join(f"W{w}:{n}" for w, n in exp.items()) +
                 " (a full week has 14-16; compare with the official schedule for missing games)")
    L += ["", "## Data quality"]
    num = [c for c in st.columns if st[c].dtype != object and c not in ("retrieved_at",)]
    nulls = ", ".join(f"{c}={int(st[c].isna().sum())}" for c in num if st[c].isna().any()) or "none"
    L.append("- NULL counts (NULL = unavailable, not zero): " + nulls)
    neg = {c: int((st[c] < 0).sum()) for c in ["passing_attempts","completions","passing_touchdowns","interceptions",
           "rushing_attempts","rushing_touchdowns","targets","receptions","receiving_touchdowns"] if c in st}
    L.append(f"- Impossible negatives (counts): {neg}")
    issues = []
    def chk(name, mask):
        for _, r in st[mask].iterrows():
            issues.append((r.game_id, r.player_id, name))
        L.append(f"- {name}: {int(mask.sum())}")
    chk("receiving_yards != 0 with 0 receptions", (st.receiving_yards.fillna(0) != 0) & (st.receptions.fillna(0) == 0))
    chk("completions > attempts", st.completions > st.passing_attempts)
    chk("receptions > targets", st.receptions > st.targets)
    chk("passing TD with 0 attempts", (st.passing_touchdowns > 0) & (st.passing_attempts.fillna(0) == 0))
    chk("rushing TD with 0 attempts", (st.rushing_touchdowns > 0) & (st.rushing_attempts.fillna(0) == 0))
    # team-assignment check
    g = games.set_index("game_id")
    bad = st[[(r.team not in (g.loc[r.game_id, "home_team"], g.loc[r.game_id, "away_team"])) if r.game_id in g.index else True
              for r in st.itertuples()]]
    L.append(f"- Players assigned to a team not in the game: {len(bad)}")
    # reconciliation: passing TDs vs receiving TDs per team-game (should match: passing TD == receiving TD)
    t = st.groupby(["game_id","team"])[["passing_touchdowns","receiving_touchdowns","passing_yards","receiving_yards"]].sum()
    mis = t[(t.passing_touchdowns != t.receiving_touchdowns)]
    L.append(f"- Team-games where passing TDs != receiving TDs: {len(mis)}")
    for (gid, tm), _ in mis.iterrows():
        issues.append((gid, tm, "pass_td != rec_td"))
    L += ["", "## Not verified (explicit limitations)",
          "- Data comes from a secondary provider (nflverse); `data_quality` = unverified_secondary.",
          "- Player totals have NOT been reconciled against official gamebooks or a second source here; "
          "scores/rosters need manual spot-check. Longest rush/reception/completion and passer rating are NULL (not provided by source).",
          "- Weather/precipitation, rest days, snaps and injury designations are not loaded."]
    now = dt.datetime.now().isoformat(timespec="seconds")
    con.execute("DELETE FROM data_quality_log WHERE detail='qa_run'")
    con.executemany("INSERT INTO data_quality_log(logged_at,game_id,player_id,check_name,detail) VALUES(?,?,?,?,?)",
                    [(now, a, b, c, "qa_run") for a, b, c in issues]); con.commit()
    return "\n".join(L)
