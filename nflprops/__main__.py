import argparse, sys
from . import db, qa, export, server


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nflprops")
    ap.add_argument("--db", default="data/nfl2026.sqlite")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="weekly update: load games/players/player_game_stats (.csv or .json) from a directory")
    i.add_argument("directory")
    i.add_argument("--correction", action="store_true", help="apply differing values as an official correction (audited)")
    i.add_argument("--reason", default="official correction")
    c = sub.add_parser("qa", help="run completeness/validation checks and print the QA report")
    c.add_argument("--expected-games", type=int)
    c.add_argument("--output")
    e = sub.add_parser("export")
    e.add_argument("outdir")
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)
    con = db.connect(a.db)
    if a.cmd == "ingest":
        r = db.ingest_dir(con, a.directory, correction=a.correction, reason=a.reason)
        print({k: (len(v) if k == "rejected" else v) for k, v in r.items()})
        for kind, _, msg in r["rejected"]:
            print(f"REJECTED {kind}: {msg}", file=sys.stderr)
        res = qa.run_checks(con)
        print("QA:", "passed" if res["passed"] else "FAILED (run `qa` for details)")
    elif a.cmd == "qa":
        text = qa.render_report(qa.run_checks(con, a.expected_games))
        if a.output:
            open(a.output, "w").write(text)
        print(text)
    elif a.cmd == "export":
        print(export.export_all(con, a.outdir))
    elif a.cmd == "serve":
        con.close()
        server.serve(a.db, a.host, a.port)


if __name__ == "__main__":
    main()
