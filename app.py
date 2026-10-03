import streamlit as st, pandas as pd, plotly.express as px, plotly.graph_objects as go
from nflprops import config, analytics as A, export
from nflprops.db import connect

st.set_page_config(page_title="NFL Prop Analytics", layout="wide")
st.caption("Historical frequencies are descriptive only. They are not probabilities, predictions, or betting advice.")

@st.cache_data(ttl=300)
def get_data(path):
    con = connect(path)
    return A.load(con), pd.read_sql("SELECT * FROM games", con)

path = st.sidebar.text_input("Database", config.DB_PATH)
df, games = get_data(path)
if df.empty:
    st.warning("Database is empty. Run: python -m nflprops.ingest"); st.stop()
page = st.sidebar.radio("Page", ["Player Explorer", "Prop Analyzer", "Parlay Builder", "Player Comparison",
                                 "Opponent Analysis", "Export"])
names = df.drop_duplicates("player_id").assign(label=lambda x: x.player_name + " (" + x.position.fillna("?") + ", " + x.team + ", " + x.player_id + ")")
label2id = dict(zip(names.label, names.player_id))
markets = list(config.MARKETS)

def pick_player(key, sub=None):
    s = names
    return label2id[st.selectbox("Player", sorted(s.label), key=key)]

def stat_table(log, col, line=None):
    w = A.windows(log, col); st.dataframe(w.rename(columns={"n": "games"}))

def chart(log, col, line=None):
    f = px.bar(log, x="week", y=col, hover_data=["opponent", "home_away"])
    if line is not None: f.add_hline(y=line, line_dash="dash", annotation_text=f"Line {line}")
    st.plotly_chart(f, width="stretch")

def dist(log, col, line):
    counts, edges = A.histogram(log[col])
    if len(counts) == 0: return
    f = go.Figure(go.Bar(x=[(edges[i] + edges[i+1]) / 2 for i in range(len(counts))], y=counts))
    if line is not None: f.add_vline(x=line, line_dash="dash", annotation_text=f"Line {line}")
    st.plotly_chart(f, width="stretch")

def game_table(log, col):
    cols = ["week", "game_date", "opponent", "home_away", "targets", "receptions", "receiving_yards",
            "receiving_touchdowns", "longest_reception", "passing_yards", "passing_touchdowns", "interceptions",
            "rushing_attempts", "rushing_yards", "rushing_touchdowns", "longest_rush"]
    st.dataframe(log[cols])

if page == "Player Explorer":
    teams = st.multiselect("Team", sorted(df.team.unique())); poss = st.multiselect("Position", sorted(df.position.dropna().unique()))
    opp = st.multiselect("Opponent", sorted(df.opponent.dropna().unique())); wk = st.multiselect("Week", sorted(df.week.unique()))
    sub = df
    if teams: sub = sub[sub.team.isin(teams)]
    if poss: sub = sub[sub.position.isin(poss)]
    n2 = sub.drop_duplicates("player_id").assign(label=lambda x: x.player_name + " (" + x.position.fillna("?") + ", " + x.team + ", " + x.player_id + ")")
    pid = dict(zip(n2.label, n2.player_id))[st.selectbox("Player", sorted(n2.label))]
    m = st.selectbox("Statistic", markets); log, col = A.player_log(df, pid, m)
    stat_table(log, col)
    if opp: log = log[log.opponent.isin(opp)]
    if wk: log = log[log.week.isin(wk)]
    chart(log, col); game_table(log, col)

elif page == "Prop Analyzer":
    pid = pick_player("pa"); m = st.selectbox("Market", markets); log, col = A.player_log(df, pid, m)
    line = st.number_input("Prop line", value=50.5, step=0.5)
    stat_table(log, col); ou = A.over_under(log, col, line)
    c = st.columns(5); c[0].metric("Sample", ou["sample_size"]); c[1].metric("Over", f"{ou['over']} ({(ou['over_pct'] or 0):.0%})")
    c[2].metric("Under", f"{ou['under']} ({(ou['under_pct'] or 0):.0%})"); c[3].metric("Push", ou["push"])
    opp = st.selectbox("Current opponent", [None] + sorted(df.team.unique()))
    st.subheader("Home/away and opponent splits"); st.dataframe(A.splits(log, col, opp))
    chart(log, col, line); dist(log, col, line)
    s = A.summarize(log[col]); st.write({k: s[k] for k in ("minimum", "maximum", "std_dev")})
    log = log.assign(result=log[col].apply(lambda v: None if pd.isna(v) else ("Over" if v > line else "Under" if v < line else "Push")))
    st.dataframe(log[["week", "opponent", "home_away", col, "result"]])

elif page == "Parlay Builder":
    st.session_state.setdefault("legs", [])
    with st.form("leg"):
        pid = pick_player("pb"); m = st.selectbox("Market", markets); side = st.radio("Side", ["Over", "Under"], horizontal=True)
        line = st.number_input("Line", value=50.5, step=0.5)
        if st.form_submit_button("Add leg"): st.session_state.legs.append(dict(player_id=pid, market=m, line=line, side=side))
    if st.button("Clear legs"): st.session_state.legs = []
    legs = st.session_state.legs
    if legs:
        infos = [A.leg_info(df, l) for l in legs]
        t = pd.DataFrame(infos).merge(names[["player_id", "player_name"]], on="player_id")
        st.dataframe(t[["player_name", "team", "market", "side", "line", "average", "median", "recent_avg", "over_pct", "under_pct", "sample_size"]])
        st.metric("Legs", len(legs))
        gbt = {}  # team -> most recent game_id (shared-game indicator uses latest games)
        for r in games.sort_values("game_date").itertuples():
            gbt[r.home_team] = r.game_id; gbt[r.away_team] = r.game_id
        st.subheader("Correlation / relationship flags (informational)")
        fl = A.correlation_flags(infos, gbt)
        st.dataframe(pd.DataFrame(fl)) if fl else st.write("No same-player/same-team relationships among legs.")
        j = A.joint_history(df, legs)
        st.subheader("Historical hit rate (not a probability)")
        st.write(f"Games where all legs' players have records: {j['shared_games']}; all legs hit: {j['all_hit']}"
                 + (f" ({j['rate']:.0%})" if j["rate"] is not None else ""))
        st.caption("Players' games rarely coincide, so this sample is usually tiny. Multiplying individual rates is not shown because it ignores correlation.")

elif page == "Player Comparison":
    sel = st.multiselect("Players", sorted(names.label)); m = st.selectbox("Market", markets); line = st.number_input("Line", value=50.5, step=0.5)
    rows = []
    for l in sel:
        log, col = A.player_log(df, label2id[l], m); s = A.summarize(log[col]); ou = A.over_under(log, col, line)
        rows.append({"Player": l, "Games": s["n"], "Season Avg": s["average"], "Last 5 Avg": A.summarize(log[col].tail(5))["average"],
                     "Median": s["median"], "Std Dev": s["std_dev"], f"Over {line} %": ou["over_pct"]})
    if rows:
        t = pd.DataFrame(rows); by = st.selectbox("Sort by", list(t.columns)); st.dataframe(t.sort_values(by, ascending=False))

elif page == "Opponent Analysis":
    st.markdown("Positions: QB=QB; RB=RB/FB/HB; WR=WR; TE=TE. Values are per-game averages **allowed** by the defense.")
    c = st.columns(3); w = c[0].selectbox("Window", [None, 3, 5, 8]); ha = c[1].selectbox("Defense venue", [None, "home", "away"])
    pg = c[2].selectbox("Position group", [None, "QB", "RB", "WR", "TE"])
    st.dataframe(A.opponent_allowed(df, w, ha, pg))

else:
    out = df.drop(columns=[], errors="ignore")
    st.write(f"{len(out)} player-game rows"); st.dataframe(out.head(100))
    tot = A.season_totals(df)
    for label, fr in [("player_game_stats", out), ("season_totals", tot)]:
        st.subheader(label); c = st.columns(3)
        c[0].download_button("CSV", export.to_csv(fr), f"{label}.csv"); c[1].download_button("JSON", export.to_json(fr), f"{label}.json")
        c[2].download_button("Excel", export.to_excel(fr), f"{label}.xlsx")
