"""
Generatore di report HTML per i risultati del Resolver.
"""

from collections import defaultdict
from models import ARISMatch


def generate_html_report(matches: list[ARISMatch], model_name: str) -> str:
    """Genera un report HTML con i risultati del matching."""

    level_colors = {
        1: ("#F0FFF4", "#38A169", "Match esatto"),
        2: ("#E6FFFA", "#028090", "Fuzzy match"),
        3: ("#FFFAF0", "#C05621", "LLM contestuale"),
        4: ("#FFF5F5", "#E53E3E", "Revisione richiesta"),
    }

    html = """<html><head><meta charset="utf-8"><style>
body{font-family:Calibri,sans-serif;margin:40px;color:#1a202c;max-width:1200px}
h1{color:#1E2761} h2{color:#028090}
table{border-collapse:collapse;width:100%;margin:16px 0}
th{background:#1E2761;color:white;padding:10px 14px;text-align:left}
td{padding:8px 14px;border-bottom:1px solid #ddd;vertical-align:top}
tr:nth-child(even){background:#f8f9fa}
.level{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:bold}
.guid{font-family:monospace;font-size:11px;color:#666}
.op{font-weight:bold;padding:2px 8px;border-radius:4px;font-size:12px}
.op-reuse{background:#F0FFF4;color:#38A169}
.op-create{background:#EBF8FF;color:#2B6CB0}
.op-flag{background:#FFF5F5;color:#E53E3E}
.warn{color:#E53E3E;font-size:12px}
.stat{background:#1E2761;color:white;padding:12px 20px;border-radius:8px;margin:8px 4px;display:inline-block}
.stat b{color:#F6AD55;font-size:22px}
</style></head><body>"""

    html += f"<h1>ARIS Resolver Report</h1>"
    html += f"<p>Modello: <b>{model_name}</b></p>"

    # Statistiche
    by_level = defaultdict(int)
    by_op = defaultdict(int)
    for m in matches:
        by_level[m.match_level] += 1
        by_op[m.operation] += 1

    html += "<div>"
    html += f'<span class="stat">Entità analizzate: <b>{len(matches)}</b></span>'
    for lv in [1, 2, 3, 4]:
        if by_level[lv] > 0:
            _, color, label = level_colors[lv]
            html += f'<span class="stat">{label}: <b>{by_level[lv]}</b></span>'
    html += "</div>"

    # Tabella per tipo di entità
    for etype, elabel in [('activity', 'Attività (Function)'),
                           ('executor', 'Esecutori (Org. Unit)'),
                           ('application', 'Applicativi'),
                           ('control', 'Controlli')]:
        ematches = [m for m in matches if m.word_entity.entity_type == etype]
        if not ematches:
            continue

        html += f"<h2>{elabel} — {len(ematches)} entità</h2>"
        html += "<table><tr><th>Word</th><th>ARIS Match</th><th>GUID</th>"
        html += "<th>Livello</th><th>Score</th><th>Operazione</th></tr>"

        for m in ematches:
            bg, color, label = level_colors.get(m.match_level, ("#FFF", "#000", "?"))
            op_class = ("op-reuse" if m.operation == "REUSE"
                        else "op-create" if m.operation == "CREATE"
                        else "op-flag")

            code_str = f"[{m.word_entity.code}] " if m.word_entity.code else ""
            html += f'<tr><td><b>{code_str}{m.word_entity.name}</b>'
            if m.warnings:
                for w in m.warnings:
                    html += f'<br><span class="warn">⚠ {w}</span>'
            html += "</td>"
            html += f'<td>{m.aris_name or "—"}</td>'
            html += f'<td class="guid">{m.aris_guid or "—"}</td>'
            html += f'<td><span class="level" style="background:{bg};color:{color}">{label}</span></td>'
            html += f'<td>{m.match_score:.0f}%</td>'
            html += f'<td><span class="op {op_class}">{m.operation}</span></td></tr>'

        html += "</table>"

    html += "</body></html>"
    return html
