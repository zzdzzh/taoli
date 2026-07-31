"""套利报告 Web 展示"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template_string, send_from_directory

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"

app = Flask(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>跨平台套利扫描 · 实时报告</title>
<meta http-equiv="refresh" content="60">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; display: flex; min-height: 100vh; }
.menu-toggle { display: none; position: fixed; top: 10px; left: 10px; z-index: 100; background: #e94560; color: #fff; border: none; width: 36px; height: 36px; border-radius: 6px; font-size: 20px; cursor: pointer; }
.sidebar { width: 260px; background: #16213e; padding: 20px; flex-shrink: 0; overflow-y: auto; transition: transform 0.3s; }
.sidebar h2 { color: #e94560; font-size: 18px; margin-bottom: 8px; }
.sidebar .subtitle { color: #888; font-size: 12px; line-height: 1.5; margin-bottom: 16px; }
.sidebar .date-group { margin-bottom: 12px; }
.sidebar .date-label { color: #aaa; font-size: 13px; margin-bottom: 4px; }
.sidebar a { display: block; color: #7ec8e3; text-decoration: none; font-size: 13px; padding: 4px 8px; border-radius: 4px; }
.sidebar a:hover { background: #0f3460; }
.sidebar a.active { background: #0f3460; color: #e94560; }
.sidebar-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 49; }
.content { flex: 1; padding: 30px; overflow-y: auto; }
.content h1 { font-size: 24px; color: #e94560; margin-bottom: 20px; }
.content h2 { font-size: 18px; color: #e94560; margin: 20px 0 10px; border-bottom: 1px solid #333; padding-bottom: 4px; }
.content h3 { font-size: 15px; color: #7ec8e3; margin: 14px 0 6px; }
.content table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; }
.content th { background: #16213e; padding: 8px 12px; text-align: left; font-size: 13px; }
.content td { padding: 6px 12px; font-size: 13px; border-bottom: 1px solid #333; }
.content tr:hover td { background: #1a1a3e; }
.content p { margin: 6px 0; font-size: 14px; line-height: 1.6; }
.content ul { margin: 8px 0 8px 20px; }
.content li { font-size: 14px; line-height: 1.6; }
.content strong { color: #e94560; }
.content hr { border: none; border-top: 1px solid #333; margin: 16px 0; }
.content code { background: #16213e; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
.content pre { background: #16213e; padding: 12px; border-radius: 6px; overflow-x: auto; }
.content a { color: #7ec8e3; }
.empty { color: #666; font-size: 15px; margin-top: 40px; text-align: center; }
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
@media (max-width: 768px) {
    body { flex-direction: column; }
    .menu-toggle { display: block; }
    .sidebar { position: fixed; top: 0; left: 0; bottom: 0; z-index: 50; width: 260px; transform: translateX(-100%); }
    .sidebar.open { transform: translateX(0); }
    .sidebar-overlay.open { display: block; }
    .content { padding: 50px 12px 20px; }
    .content h1 { font-size: 20px; }
    .content h2 { font-size: 16px; }
    .content h3 { font-size: 14px; }
    .content th, .content td { padding: 6px 8px; font-size: 12px; }
    .content p, .content li { font-size: 13px; }
}
</style>
<script>
function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('open');
    document.querySelector('.sidebar-overlay').classList.toggle('open');
}
</script>
</head>
<body>
<button class="menu-toggle" onclick="toggleSidebar()">☰</button>
<div class="sidebar-overlay" onclick="toggleSidebar()"></div>
<div class="sidebar">
    <h2>套利扫描</h2>
    <div class="subtitle">Odds API + Polymarket + Kalshi + Myriad + Betfair<br>每 60 秒自动刷新页面</div>
    <div class="date-group">
        <a href="/" class="{{ 'active' if not selected else '' }}">最新报告</a>
    </div>
    {% for date, files in dates.items() %}
    <div class="date-group">
        <div class="date-label">{{ date }}</div>
        {% for f in files %}
        <a href="/report/{{ f }}" class="{{ 'active' if selected == f else '' }}">{{ f.replace('.md', '')[-8:] }}</a>
        {% endfor %}
    </div>
    {% endfor %}
</div>
<div class="content">
{{ content|safe if content else '<div class="empty">暂无报告数据<br>请在服务器运行：python3 simulate.py live</div>' }}
</div>
</body>
</html>"""


def md_to_html(text: str) -> str:
    lines = text.split("\n")
    html: list[str] = []
    in_table = False
    in_code = False
    _header_cells: list[str] = []

    for line in lines:
        if line.startswith("```"):
            if in_code:
                html.append("</code></pre>")
                in_code = False
            else:
                html.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            html.append(line)
            continue

        if line.startswith("### "):
            html.append(f"<h3>{line[4:]}</h3>")
            continue
        if line.startswith("## "):
            html.append(f"<h2>{line[3:]}</h2>")
            continue
        if line.startswith("# "):
            html.append(f"<h1>{line[2:]}</h1>")
            continue

        if line.startswith("---"):
            html.append("<hr>")
            continue

        if line.startswith("|"):
            if not in_table:
                in_table = True
                _header_cells = []
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(c.replace("-", "").replace(":", "").strip() == "" for c in cells):
                html.append("<tr>" + "".join(f"<th>{c}</th>" for c in _header_cells) + "</tr>")
                html.append('<div class="table-wrap"><table>')
                continue
            if not _header_cells:
                _header_cells = cells
                continue
            html.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        else:
            if in_table:
                html.append("</table></div>")
                in_table = False
            elif html and html[-1] == '<div class="table-wrap"><table>':
                html.append("</table></div>")

        if line.startswith("- "):
            html.append(f"<li>{_inline(line[2:])}</li>")
            continue
        if re.match(r"^\d+\. ", line):
            stripped = re.sub(r"^\d+\. ", "", line)
            html.append(f"<li>{_inline(stripped)}</li>")
            continue

        if line.strip() == "":
            html.append("")
            continue

        html.append(f"<p>{_inline(line)}</p>")

    if in_table:
        html.append("</table>")
    return "\n".join(html)


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _list_reports() -> dict[str, list[str]]:
    dates: dict[str, list[str]] = {}
    if not REPORTS_DIR.exists():
        return dates
    for f in sorted(REPORTS_DIR.glob("*.md"), reverse=True):
        if f.name == "latest.md":
            continue
        ts = f.stem.replace("live_paper_", "")
        if len(ts) >= 8:
            date_str = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
            dates.setdefault(date_str, []).append(f.name)
    return dates


@app.route("/")
def index():
    latest = REPORTS_DIR / "latest.md"
    content = ""
    if latest.exists():
        content = md_to_html(latest.read_text(encoding="utf-8"))
    dates = _list_reports()
    return render_template_string(HTML_TEMPLATE, content=content, dates=dates, selected="")


@app.route("/report/<path:filename>")
def view_report(filename: str):
    filepath = REPORTS_DIR / filename
    if not filepath.exists():
        return "报告不存在", 404
    content = md_to_html(filepath.read_text(encoding="utf-8"))
    dates = _list_reports()
    return render_template_string(HTML_TEMPLATE, content=content, dates=dates, selected=filename)


if __name__ == "__main__":
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"套利报告 Web 服务: http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8081, debug=False)