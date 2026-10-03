"""Dashboard server (stdlib only). Binds to localhost by default; read-only API."""
import json, sqlite3, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from . import analytics, export, qa

STATIC = Path(__file__).with_name("static")


def make_handler(db_path):
    class H(BaseHTTPRequestHandler):
        def _con(self):
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            return con

        def _send(self, body, ctype="application/json", status=200, headers=None):
            if isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=200):
            self._send(json.dumps(obj, default=str), status=status)

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path in ("/", "/index.html"):
                    return self._send((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                con = self._con()
                try:
                    return self.route(con, u.path, q)
                finally:
                    con.close()
            except (ValueError, KeyError) as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa
                self._json({"error": "server error"}, 500)

        def do_POST(self):
            u = urlparse(self.path)
            if u.path != "/api/parlay":
                return self._json({"error": "not found"}, 404)
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 100000)
                legs = json.loads(self.rfile.read(n))["legs"]
                for l in legs:
                    l["line"] = float(l["line"])
                con = self._con()
                try:
                    self._json(analytics.parlay(con, legs))
                finally:
                    con.close()
            except (ValueError, KeyError, TypeError) as e:
                self._json({"error": f"bad request: {e}"}, 400)

        def route(self, con, path, q):
            if path == "/api/meta":
                return self._json({
                    "markets": analytics.MARKETS,
                    "players": [dict(r) for r in con.execute("SELECT player_id,player_name,position,current_team FROM players ORDER BY player_name")],
                    "teams": [r[0] for r in con.execute("SELECT home_team FROM games UNION SELECT away_team FROM games ORDER BY 1")],
                    "weeks": [r[0] for r in con.execute("SELECT DISTINCT week FROM games WHERE status='final' ORDER BY 1")]})
            if path == "/api/player":
                line = float(q["line"]) if q.get("line") not in (None, "") else None
                prof = analytics.player_profile(con, q["player_id"], q["market"], line, q.get("opponent") or None)
                if q.get("week"):
                    prof["games"] = [g for g in prof["games"] if g["week"] == int(q["week"])]
                return self._json(prof)
            if path == "/api/compare":
                line = float(q["line"]) if q.get("line") not in (None, "") else None
                return self._json(analytics.compare(con, q["player_ids"].split(","), q["market"], line))
            if path == "/api/opponents":
                return self._json(analytics.opponent_allowed(
                    con, int(q["window"]) if q.get("window") else None, q.get("home_away") or None, q.get("position_group") or None))
            if path == "/api/qa":
                return self._json(qa.run_checks(con))
            if path.startswith("/api/export."):
                fmt = path.rsplit(".", 1)[1]
                data = export.datasets(con)
                if fmt == "json":
                    return self._send(export.to_json(data), headers={"Content-Disposition": "attachment; filename=nfl_2026.json"})
                if fmt == "xlsx":
                    return self._send(export.to_xlsx(data), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                      headers={"Content-Disposition": "attachment; filename=nfl_2026.xlsx"})
                if fmt == "csv":
                    ds = q.get("dataset", "player_game_stats")
                    if ds not in data:
                        raise ValueError("unknown dataset")
                    return self._send(export.to_csv(data[ds]), "text/csv", headers={"Content-Disposition": f"attachment; filename={ds}.csv"})
            self._json({"error": "not found"}, 404)

        def log_message(self, *a):
            pass
    return H


def serve(db_path, host="127.0.0.1", port=8000):
    srv = ThreadingHTTPServer((host, port), make_handler(db_path))
    print(f"Dashboard at http://{host}:{port}")
    srv.serve_forever()
