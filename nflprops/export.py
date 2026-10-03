"""CSV / JSON / Excel export of raw + derived data with sources and quality flags."""
import csv, json, zipfile, io
from pathlib import Path
from xml.sax.saxutils import escape
from . import analytics


def datasets(con):
    q = lambda s: [dict(r) for r in con.execute(s)]
    return {
        "games": q("SELECT * FROM games ORDER BY week, game_id"),
        "players": q("SELECT * FROM players ORDER BY player_id"),
        "player_game_stats": q("SELECT s.*, g.week, g.game_date, g.home_team AS home_team_id, g.away_team AS away_team_id "
                               "FROM player_game_stats s JOIN games g USING(game_id) ORDER BY g.week, s.game_id, s.player_id"),
        "season_totals": analytics.season_totals(con),
        "rolling_stats": analytics.rolling_table(con),
        "data_quality_log": q("SELECT * FROM data_quality_log"),
        "audit_log": q("SELECT * FROM audit_log"),
    }


def to_csv(rows):
    if not rows:
        return ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def to_json(data):
    return json.dumps(data, indent=2, default=str)


def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def to_xlsx(data):
    """Minimal dependency-free .xlsx writer (inline strings). Returns bytes. NULL -> empty cell."""
    names = list(data)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
                   "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(names))) + "</Types>")
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' +
                   "".join(f'<sheet name="{escape(n[:31])}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
                   "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(names))) + "</Relationships>")
        for i, n in enumerate(names):
            rows = data[n]
            cols = list(rows[0]) if rows else []
            def cell(r, c, v):
                ref = f"{_col(c)}{r}"
                if v is None:
                    return ""
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return f'<c r="{ref}"><v>{v}</v></c>'
                return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
            body = ""
            if cols:
                body += '<row r="1">' + "".join(cell(1, c, k) for c, k in enumerate(cols)) + "</row>"
                for ri, row in enumerate(rows, 2):
                    body += f'<row r="{ri}">' + "".join(cell(ri, c, row[k]) for c, k in enumerate(cols)) + "</row>"
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + body + "</sheetData></worksheet>")
    return out.getvalue()


def export_all(con, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    data = datasets(con)
    for n, rows in data.items():
        (outdir / f"{n}.csv").write_text(to_csv(rows))
    (outdir / "nfl_2026.json").write_text(to_json(data))
    (outdir / "nfl_2026.xlsx").write_bytes(to_xlsx(data))
    return sorted(p.name for p in outdir.iterdir())
