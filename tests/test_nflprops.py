"""Tests use SYNTHETIC fixtures (fake teams AAA/BBB/CCC, fake players). Not real NFL data."""
import io, json, unittest, zipfile
from nflprops import db, analytics, qa, export

SRC = {"source": "test-fixture", "source_url": "n/a", "retrieved_on": "2000-01-01"}


def game(i, week, h, a, hs, as_):
    return {"game_id": f"G{i}", "season": 2026, "week": week, "home_team": h, "away_team": a, "home_score": hs,
            "away_score": as_, "status": "final", "overtime": 0, **SRC}


def stat(g, p, team, **k):
    return {"game_id": g, "player_id": p, "team": team, **SRC, **k}


class Base(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")
        games = [game(1, 1, "AAA", "BBB", 20, 10), game(2, 2, "CCC", "AAA", 7, 7), game(3, 3, "AAA", "CCC", 3, 0)]
        players = [{"player_id": "P1", "player_name": "Sam Smith", "position": "QB", "current_team": "AAA"},
                   {"player_id": "P2", "player_name": "Sam Smith", "position": "WR", "current_team": "AAA"},
                   {"player_id": "P3", "player_name": "Rex Roe", "position": "QB", "current_team": "BBB"}]
        stats = [stat("G1", "P1", "AAA", passing_attempts=30, completions=20, passing_yards=100, passing_touchdowns=1),
                 stat("G1", "P2", "AAA", targets=5, receptions=4, receiving_yards=100, receiving_touchdowns=1),
                 stat("G2", "P1", "AAA", passing_attempts=30, completions=20, passing_yards=200, passing_touchdowns=0),
                 stat("G2", "P2", "AAA", targets=5, receptions=4, receiving_yards=200),
                 stat("G3", "P1", "AAA", passing_attempts=30, completions=20, passing_yards=300),
                 stat("G3", "P2", "AAA", targets=5, receptions=4, receiving_yards=300, receiving_touchdowns=0),
                 stat("G1", "P3", "BBB", passing_attempts=10, completions=5, passing_yards=50)]
        self.res = db.ingest(self.con, games, players, stats)


class TestIngest(Base):
    def test_loaded(self):
        self.assertEqual(self.res["rejected"], [])
        self.assertEqual(self.con.execute("SELECT winning_team FROM games WHERE game_id='G2'").fetchone()[0], "TIE")

    def test_null_not_zero(self):
        r = self.con.execute("SELECT receiving_touchdowns FROM player_game_stats WHERE game_id='G2' AND player_id='P2'").fetchone()
        self.assertIsNone(r[0])
        r = self.con.execute("SELECT receiving_touchdowns FROM player_game_stats WHERE game_id='G3' AND player_id='P2'").fetchone()
        self.assertEqual(r[0], 0)

    def test_empty_string_is_null(self):
        db.ingest(self.con, stats=[stat("G3", "P3", "CCC", passing_yards="")])
        r = self.con.execute("SELECT passing_yards FROM player_game_stats WHERE game_id='G3' AND player_id='P3'").fetchone()
        self.assertIsNone(r[0])

    def test_rejects_bad_rows(self):
        r = db.ingest(self.con, stats=[stat("G9", "P1", "AAA"), stat("G3", "P1", "ZZZ"), stat("G3", "P3", "AAA", passing_yards=-1)])
        self.assertEqual(len(r["rejected"]), 3)

    def test_conflict_not_overwritten_and_correction_audited(self):
        r = db.ingest(self.con, stats=[stat("G1", "P1", "AAA", passing_yards=999)])
        self.assertEqual(r["conflict"], 1)
        self.assertEqual(self.con.execute("SELECT passing_yards FROM player_game_stats WHERE game_id='G1' AND player_id='P1'").fetchone()[0], 100)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM data_quality_log WHERE severity='conflict'").fetchone()[0], 1)
        db.ingest(self.con, stats=[stat("G1", "P1", "AAA", passing_yards=101)], correction=True)
        self.assertEqual(self.con.execute("SELECT passing_yards FROM player_game_stats WHERE game_id='G1' AND player_id='P1'").fetchone()[0], 101)
        a = self.con.execute("SELECT old_value,new_value FROM audit_log WHERE field='passing_yards'").fetchone()
        self.assertEqual((a[0], a[1]), ("100", "101"))

    def test_idempotent(self):
        r = db.ingest(self.con, stats=[stat("G1", "P1", "AAA", passing_yards=100)])
        self.assertEqual(r["unchanged"], 1)


class TestAnalytics(Base):
    def test_windows_and_hit_rate(self):
        prof = analytics.player_profile(self.con, "P2", "receiving_yards", 150.5)
        self.assertEqual(prof["windows"]["season"]["avg"], 200)
        self.assertEqual(prof["windows"]["last3"]["median"], 200)
        self.assertEqual(prof["windows"]["last5"]["n"], 3)
        self.assertEqual(prof["hit_rate"]["over"], 2)
        self.assertAlmostEqual(prof["hit_rate"]["under_pct"], 1 / 3)
        self.assertEqual(prof["home"]["n"], 2)

    def test_null_excluded_from_average(self):
        s = analytics.summarize([None, 4, 6])
        self.assertEqual((s["n"], s["avg"]), (2, 5))
        self.assertEqual(analytics.summarize([None])["avg"], None)

    def test_opponent_allowed(self):
        t = analytics.opponent_allowed(self.con)
        self.assertEqual(t["BBB"]["passing_yards_total"], 100)  # AAA's QB vs BBB defense
        self.assertEqual(analytics.opponent_allowed(self.con, position_group="WR")["BBB"]["receiving_yards_total"], 100)

    def test_parlay_flags_and_no_product(self):
        r = analytics.parlay(self.con, [{"player_id": "P1", "market": "passing_yards", "line": 150.5},
                                        {"player_id": "P2", "market": "receiving_yards", "line": 150.5}])
        types = {f["type"] for f in r["correlation_flags"]}
        self.assertIn("same_team", types)
        self.assertEqual(r["combined_historical"]["games_where_all_legs_hit"], 2)
        self.assertNotIn("probability", r["combined_historical"])
        r2 = analytics.parlay(self.con, [{"player_id": "P1", "market": "passing_yards", "line": 1, "side": "over"},
                                         {"player_id": "P3", "market": "passing_yards", "line": 1, "side": "under"}])
        self.assertEqual(r2["combined_historical"]["games_where_all_legs_have_data"], 1)

    def test_bad_market(self):
        with self.assertRaises(ValueError):
            analytics.hit_rate([], "bogus", 1)


class TestQAExport(Base):
    def test_qa_flags_mismatch(self):
        res = qa.run_checks(self.con, expected_games_through_week=4)
        self.assertFalse(res["passed"])  # missing game
        msgs = " ".join(i["message"] for i in res["issues"])
        self.assertIn("players share this name", msgs)
        self.assertEqual(res["coverage"]["unique_players"], 3)

    def test_qa_catches_impossible(self):
        self.con.execute("UPDATE player_game_stats SET receptions=9 WHERE game_id='G1' AND player_id='P2'")
        msgs = " ".join(i["message"] for i in qa.run_checks(self.con)["issues"])
        self.assertIn("receptions exceed targets", msgs)

    def test_export(self):
        data = export.datasets(self.con)
        self.assertEqual(len(data["player_game_stats"]), 7)
        self.assertIn("source", export.to_csv(data["player_game_stats"]).splitlines()[0])
        self.assertEqual(len(json.loads(export.to_json(data))["games"]), 3)
        z = zipfile.ZipFile(io.BytesIO(export.to_xlsx(data)))
        self.assertIn("xl/worksheets/sheet1.xml", z.namelist())
        import xml.dom.minidom as m
        for n in z.namelist():
            m.parseString(z.read(n))


if __name__ == "__main__":
    unittest.main()
