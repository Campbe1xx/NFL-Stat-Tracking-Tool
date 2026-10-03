"""Database creation and weekly ingest (CSV/JSON).

Ingest never silently overwrites: a differing value for an existing record is only
applied with correction=True (an official statistical correction) and the previous
value is preserved in audit_log. Otherwise the conflict is written to data_quality_log.
"""
import csv, json, sqlite3, datetime
from pathlib import Path

STAT_INT = ["passing_attempts", "completions", "passing_yards", "passing_touchdowns", "interceptions",
            "longest_completion", "rushing_attempts", "rushing_yards", "rushing_touchdowns", "longest_rush",
            "targets", "receptions", "receiving_yards", "receiving_touchdowns", "longest_reception"]
STAT_REAL = ["passer_rating"]
STAT_FIELDS = STAT_INT + STAT_REAL
GAME_INT = ["season", "week", "home_score", "away_score", "overtime"]
GAME_REAL = ["temperature_f", "wind_mph", "closing_spread", "closing_total"]
GAME_TEXT = ["game_date", "day", "start_time", "home_team", "away_team", "winning_team", "status", "stadium",
             "indoor_outdoor", "surface", "weather", "precipitation", "betting_source", "source", "source_url",
             "retrieved_on", "quality_status"]
PLAYER_FIELDS = ["player_name", "first_name", "last_name", "position", "current_team", "jersey_number"]
PSTAT_TEXT = ["team", "opponent", "home_away", "position", "source", "source_url", "retrieved_on", "quality_status"]


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript((Path(__file__).with_name("schema.sql")).read_text())
    return con


def _conv(v, kind):
    """Empty -> NULL (never 0). Raises ValueError on bad numerics."""
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if v == "" or v.upper() in ("NULL", "NA", "N/A", "NONE"):
            return None
    if kind == "int":
        f = float(v)
        if f != int(f):
            raise ValueError(f"non-integer value {v!r}")
        return int(f)
    if kind == "real":
        return float(v)
    return str(v)


def _log(con, severity, msg, game_id=None, player_id=None, field=None):
    con.execute("INSERT INTO data_quality_log(logged_at,game_id,player_id,field,severity,message) VALUES(?,?,?,?,?,?)",
                (now(), game_id, player_id, field, severity, msg))


def _upsert(con, table, keycols, rec, correction, reason):
    where = " AND ".join(f"{k}=?" for k in keycols)
    kv = [rec[k] for k in keycols]
    old = con.execute(f"SELECT * FROM {table} WHERE {where}", kv).fetchone()
    keystr = "|".join(str(x) for x in kv)
    if old is None:
        cols = list(rec)
        con.execute(f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [rec[c] for c in cols])
        return "inserted"
    diffs = {c: v for c, v in rec.items() if c not in keycols and old[c] != v}
    if not diffs:
        return "unchanged"
    # A scheduled game becoming final, or filling previously-NULL values, is a normal update.
    real = {c: v for c, v in diffs.items() if old[c] is not None}
    progress = table == "games" and old["status"] != "final"
    if real and not correction and not progress:
        for c, v in real.items():
            _log(con, "conflict", f"{table} {keystr}: incoming {c}={v!r} conflicts with stored {old[c]!r}; not applied",
                 rec.get("game_id"), rec.get("player_id"), c)
        diffs = {c: v for c, v in diffs.items() if old[c] is None}
        if not diffs:
            return "conflict"
    for c, v in diffs.items():
        con.execute("INSERT INTO audit_log(changed_at,table_name,key,field,old_value,new_value,reason) VALUES(?,?,?,?,?,?,?)",
                    (now(), table, keystr, c, None if old[c] is None else str(old[c]), None if v is None else str(v),
                     reason if (correction or progress) else "fill missing value"))
    sets = ",".join(f"{c}=?" for c in diffs)
    con.execute(f"UPDATE {table} SET {sets} WHERE {where}", list(diffs.values()) + kv)
    return "updated"


def _read(path):
    path = Path(path)
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text())
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _clean(row, ints, reals, texts):
    out = {}
    for k in ints:
        if k in row: out[k] = _conv(row[k], "int")
    for k in reals:
        if k in row: out[k] = _conv(row[k], "real")
    for k in texts:
        if k in row: out[k] = _conv(row[k], "text")
    return out


def ingest(con, games=None, players=None, stats=None, correction=False, reason="official correction"):
    """Ingest lists of dict rows. Returns counts and rejected rows (never silently dropped)."""
    res = {"inserted": 0, "updated": 0, "unchanged": 0, "conflict": 0, "rejected": []}

    def bump(r):
        res[r] += 1

    for g in games or []:
        try:
            rec = {"game_id": _conv(g["game_id"], "text"), **_clean(g, GAME_INT, GAME_REAL, GAME_TEXT)}
            if not rec.get("game_id") or not rec.get("source"):
                raise ValueError("game_id and source are required")
            if rec.get("status") is None:
                rec["status"] = "scheduled"
            if rec["status"] == "final" and rec.get("home_score") is not None and rec.get("away_score") is not None \
                    and not rec.get("winning_team"):
                hs, as_ = rec["home_score"], rec["away_score"]
                rec["winning_team"] = rec["home_team"] if hs > as_ else rec["away_team"] if as_ > hs else "TIE"
            bump(_upsert(con, "games", ["game_id"], rec, correction, reason))
        except (KeyError, ValueError, TypeError) as e:
            res["rejected"].append(("game", g, str(e)))
    for p in players or []:
        try:
            rec = {"player_id": _conv(p["player_id"], "text"), **_clean(p, ["jersey_number"], [], [f for f in PLAYER_FIELDS if f != "jersey_number"])}
            if not rec["player_id"] or not rec.get("player_name"):
                raise ValueError("player_id and player_name are required")
            bump(_upsert(con, "players", ["player_id"], rec, True, "player attribute update (team/position changes)"))
        except (KeyError, ValueError, TypeError) as e:
            res["rejected"].append(("player", p, str(e)))
    for s in stats or []:
        try:
            rec = {"game_id": _conv(s["game_id"], "text"), "player_id": _conv(s["player_id"], "text"),
                   **_clean(s, STAT_INT, STAT_REAL, PSTAT_TEXT)}
            if not rec.get("source") or not rec.get("team"):
                raise ValueError("team and source are required")
            if not con.execute("SELECT 1 FROM games WHERE game_id=?", (rec["game_id"],)).fetchone():
                raise ValueError("unknown game_id")
            prow = con.execute("SELECT position FROM players WHERE player_id=?", (rec["player_id"],)).fetchone()
            if prow is None:
                raise ValueError("unknown player_id")
            if rec.get("position") is None and prow["position"]:
                rec["position"] = prow["position"]
            g = con.execute("SELECT home_team,away_team FROM games WHERE game_id=?", (rec["game_id"],)).fetchone()
            if rec["team"] == g["home_team"]:
                ha, opp = "home", g["away_team"]
            elif rec["team"] == g["away_team"]:
                ha, opp = "away", g["home_team"]
            else:
                raise ValueError(f"team {rec['team']} did not play in game {rec['game_id']}")
            rec["home_away"], rec["opponent"] = ha, opp  # derived from the game, not trusted from input
            for k in STAT_FIELDS:
                if rec.get(k) is not None and rec[k] < 0:
                    raise ValueError(f"negative {k}")
            bump(_upsert(con, "player_game_stats", ["game_id", "player_id"], rec, correction, reason))
        except (KeyError, ValueError, TypeError) as e:
            res["rejected"].append(("stat", s, str(e)))
    for kind, row, msg in res["rejected"]:
        _log(con, "rejected", f"{kind} row rejected: {msg}: {json.dumps(row, default=str)[:300]}")
    con.commit()
    return res


def ingest_dir(con, directory, **kw):
    d = Path(directory)

    def load(name):
        for ext in (".csv", ".json"):
            if (d / (name + ext)).exists():
                return _read(d / (name + ext))
        return None
    return ingest(con, load("games"), load("players"), load("player_game_stats"), **kw)
