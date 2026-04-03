"""Static HTML dashboard generator.

Reads the SQLite database and generates a static site in an output directory
that can be deployed to Netlify, GitHub Pages, or any static host.
"""

import json
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from localizer.db import Database


SOURCE_LABELS = {
    "portland": "City of Portland",
    "multnomah": "Multnomah County",
    "metro": "Oregon Metro",
    "trimet": "TriMet",
    "port": "Port of Portland",
    "oregonbuys": "OregonBuys (State)",
}

TYPE_COLORS = {
    "RFP": "#059669", "RFI": "#2563eb", "RFQ": "#7c3aed",
    "RFS": "#0891b2", "IFB": "#d97706", "ITB": "#d97706",
    "ITN": "#dc2626", "SOQ": "#4f46e5", "SOW": "#0d9488",
    "PSS": "#be185d", "BOA": "#64748b", "IDIQ": "#64748b",
}


def generate_site(db: Database, output_dir: Path):
    """Generate a complete static site from the database."""
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rfps = db.get_open_rfps()
    now = datetime.utcnow()
    since_7d = (now - timedelta(days=7)).isoformat()
    new_rfps = db.get_new_rfps(since=since_7d)
    history = db.get_scrape_history(limit=50)

    # Stats
    sources = {}
    types = {}
    for r in all_rfps:
        src = r["source"]
        sources[src] = sources.get(src, 0) + 1
        t = r.get("solicitation_type") or "other"
        types[t] = types.get(t, 0) + 1

    new_ids = {r["id"] for r in new_rfps}

    # Build the index page
    html = _render_page(all_rfps, new_ids, sources, types, history, now)
    (output_dir / "index.html").write_text(html)

    # Write RFP data as JSON for potential future JS interactivity
    rfps_json = json.dumps(all_rfps, indent=2, default=str)
    (output_dir / "data.json").write_text(rfps_json)

    # Netlify config
    (output_dir / "_redirects").write_text("/* /index.html 200\n")

    return len(all_rfps)


def _render_page(rfps, new_ids, sources, types, history, now):
    now_str = now.strftime("%B %d, %Y at %H:%M UTC")
    total = len(rfps)
    new_count = len(new_ids)

    # Deadline warnings
    upcoming = []
    for r in rfps:
        if r.get("due_date"):
            try:
                due = datetime.fromisoformat(r["due_date"])
                days = (due - now).days
                if 0 <= days <= 7:
                    upcoming.append((r, days))
            except ValueError:
                pass
    upcoming.sort(key=lambda x: x[1])

    rfp_rows = []
    for r in rfps:
        is_new = r["id"] in new_ids
        rfp_rows.append(_render_rfp_row(r, is_new, now))

    source_pills = []
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        label = SOURCE_LABELS.get(src, src)
        source_pills.append(
            f'<span class="pill source-pill" data-source="{e(src)}">'
            f'{e(label)} <strong>{count}</strong></span>'
        )

    type_pills = []
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        color = TYPE_COLORS.get(t, "#64748b")
        type_pills.append(
            f'<span class="pill type-pill" data-type="{e(t)}" '
            f'style="background:{color}">{e(t)} <strong>{count}</strong></span>'
        )

    upcoming_html = ""
    if upcoming:
        items = []
        for r, days in upcoming[:5]:
            label = "TODAY" if days == 0 else f"{days}d"
            items.append(
                f'<div class="deadline-item">'
                f'<span class="deadline-days {"urgent" if days <= 2 else ""}">{label}</span>'
                f'<span class="deadline-title">{e(r["title"][:60])}</span>'
                f'<span class="deadline-source">{e(SOURCE_LABELS.get(r["source"], r["source"]))}</span>'
                f'</div>'
            )
        upcoming_html = f'''
        <div class="card deadline-card">
            <h2>Closing Soon</h2>
            {"".join(items)}
        </div>'''

    history_rows = []
    for h in history[:10]:
        status_cls = "success" if h["status"] == "success" else "error"
        finished = h.get("finished_at") or ""
        if finished:
            try:
                finished = datetime.fromisoformat(finished).strftime("%m/%d %H:%M")
            except ValueError:
                pass
        history_rows.append(
            f'<tr>'
            f'<td>{e(SOURCE_LABELS.get(h["source"], h["source"]))}</td>'
            f'<td><span class="status-{status_cls}">{e(h["status"])}</span></td>'
            f'<td>{h["rfps_found"]}</td>'
            f'<td>{h["rfps_new"]}</td>'
            f'<td class="dim">{e(finished)}</td>'
            f'</tr>'
        )

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Localizer &mdash; Portland Procurement Monitor</title>
<style>
:root {{
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #e2e8f0; --text-dim: #94a3b8; --accent: #38bdf8;
    --green: #34d399; --red: #f87171; --yellow: #fbbf24;
    --border: #475569;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    line-height: 1.5; padding: 0;
}}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
header {{
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 20px 0; margin-bottom: 24px;
}}
header .container {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
h1 {{ font-size: 1.5rem; font-weight: 700; }}
h1 span {{ color: var(--accent); }}
.updated {{ color: var(--text-dim); font-size: 0.85rem; }}
.stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }}
.stat {{
    background: var(--surface); border-radius: 8px; padding: 16px 20px;
    flex: 1; min-width: 140px;
}}
.stat-value {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
.stat-label {{ color: var(--text-dim); font-size: 0.85rem; }}
.filters {{
    display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; align-items: center;
}}
.search-box {{
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 8px 14px; border-radius: 6px; font-size: 0.9rem; width: 260px;
}}
.search-box::placeholder {{ color: var(--text-dim); }}
.pill {{
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-size: 0.8rem; cursor: pointer; color: white;
    background: var(--surface2); transition: opacity 0.15s;
    user-select: none;
}}
.pill:hover {{ opacity: 0.85; }}
.pill.active {{ box-shadow: 0 0 0 2px var(--accent); }}
.pill strong {{ margin-left: 4px; }}
.source-pill {{ background: var(--surface2); }}
.card {{
    background: var(--surface); border-radius: 8px; padding: 20px;
    margin-bottom: 20px; border: 1px solid var(--border);
}}
.card h2 {{ font-size: 1.1rem; margin-bottom: 12px; color: var(--text-dim); }}
.deadline-card {{ border-left: 3px solid var(--yellow); }}
.deadline-item {{
    display: flex; align-items: center; gap: 12px; padding: 6px 0;
    border-bottom: 1px solid var(--border);
}}
.deadline-item:last-child {{ border-bottom: none; }}
.deadline-days {{
    background: var(--yellow); color: #000; font-weight: 700; font-size: 0.8rem;
    padding: 2px 8px; border-radius: 4px; min-width: 48px; text-align: center;
}}
.deadline-days.urgent {{ background: var(--red); color: white; }}
.deadline-title {{ flex: 1; font-weight: 500; }}
.deadline-source {{ color: var(--text-dim); font-size: 0.85rem; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{
    text-align: left; padding: 10px 12px; font-size: 0.8rem; font-weight: 600;
    color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em;
    border-bottom: 2px solid var(--border); position: sticky; top: 0;
    background: var(--surface); cursor: pointer;
}}
th:hover {{ color: var(--accent); }}
td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 0.9rem; vertical-align: top; }}
tr.rfp-row:hover {{ background: var(--surface2); }}
tr.rfp-row.is-new {{ border-left: 3px solid var(--green); }}
.rfp-title {{ font-weight: 500; }}
.rfp-title a {{ color: var(--accent); text-decoration: none; }}
.rfp-title a:hover {{ text-decoration: underline; }}
.type-badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 0.75rem; font-weight: 700; color: white;
}}
.new-badge {{
    display: inline-block; background: var(--green); color: #000;
    padding: 1px 6px; border-radius: 3px; font-size: 0.7rem; font-weight: 700;
    margin-left: 6px;
}}
.due-date {{ white-space: nowrap; }}
.due-date.overdue {{ color: var(--red); text-decoration: line-through; }}
.due-date.soon {{ color: var(--red); font-weight: 700; }}
.due-date.upcoming {{ color: var(--yellow); }}
.dim {{ color: var(--text-dim); }}
.status-success {{ color: var(--green); }}
.status-error {{ color: var(--red); }}
.history-table {{ margin-top: 24px; }}
.history-table table {{ font-size: 0.85rem; }}
.empty-state {{
    text-align: center; padding: 60px 20px; color: var(--text-dim);
}}
.empty-state h2 {{ font-size: 1.3rem; margin-bottom: 8px; }}
#rfp-count {{ color: var(--text-dim); font-size: 0.85rem; margin-bottom: 8px; }}
@media (max-width: 768px) {{
    .container {{ padding: 12px; }}
    .stats {{ gap: 8px; }}
    .stat {{ min-width: 100px; padding: 12px; }}
    .stat-value {{ font-size: 1.5rem; }}
    .search-box {{ width: 100%; }}
    th, td {{ padding: 8px 6px; font-size: 0.8rem; }}
    .hide-mobile {{ display: none; }}
}}
</style>
</head>
<body>
<header>
    <div class="container">
        <h1><span>Localizer</span> Portland Procurement Monitor</h1>
        <div class="updated">Updated {e(now_str)}</div>
    </div>
</header>

<div class="container">
    <div class="stats">
        <div class="stat">
            <div class="stat-value">{total}</div>
            <div class="stat-label">Open Opportunities</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color: var(--green)">{new_count}</div>
            <div class="stat-label">New This Week</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color: var(--yellow)">{len(upcoming)}</div>
            <div class="stat-label">Closing Within 7 Days</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(sources)}</div>
            <div class="stat-label">Sources Active</div>
        </div>
    </div>

    {upcoming_html}

    <div class="filters">
        <input type="text" class="search-box" id="search" placeholder="Search opportunities...">
        {" ".join(source_pills)}
        {" ".join(type_pills)}
    </div>

    <div id="rfp-count"></div>

    <div class="card" style="padding: 0; overflow-x: auto;">
        <table id="rfp-table">
            <thead>
                <tr>
                    <th data-sort="source">Source</th>
                    <th data-sort="type">Type</th>
                    <th data-sort="title">Title</th>
                    <th data-sort="due" class="hide-mobile">Due Date</th>
                    <th data-sort="seen" class="hide-mobile">Found</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rfp_rows) if rfp_rows else '<tr><td colspan="5" class="empty-state"><h2>No opportunities yet</h2><p>Scraper has not run yet. Trigger a manual run in GitHub Actions.</p></td></tr>'}
            </tbody>
        </table>
    </div>

    <details class="history-table">
        <summary style="cursor:pointer; color: var(--text-dim); margin-bottom: 12px;">Scrape History</summary>
        <div class="card" style="padding: 0; overflow-x: auto;">
            <table>
                <thead><tr><th>Source</th><th>Status</th><th>Found</th><th>New</th><th>When</th></tr></thead>
                <tbody>{"".join(history_rows)}</tbody>
            </table>
        </div>
    </details>
</div>

<script>
const rows = document.querySelectorAll('.rfp-row');
const search = document.getElementById('search');
const countEl = document.getElementById('rfp-count');
let activeSource = null, activeType = null;

function updateCount() {{
    const visible = document.querySelectorAll('.rfp-row:not([style*="display: none"])').length;
    countEl.textContent = `Showing ${{visible}} of ${{rows.length}} opportunities`;
}}

function filterRows() {{
    const q = search.value.toLowerCase();
    rows.forEach(row => {{
        const text = row.textContent.toLowerCase();
        const src = row.dataset.source;
        const type = row.dataset.type;
        const matchSearch = !q || text.includes(q);
        const matchSource = !activeSource || src === activeSource;
        const matchType = !activeType || type === activeType;
        row.style.display = (matchSearch && matchSource && matchType) ? '' : 'none';
    }});
    updateCount();
}}

search.addEventListener('input', filterRows);

document.querySelectorAll('.source-pill').forEach(pill => {{
    pill.addEventListener('click', () => {{
        const src = pill.dataset.source;
        if (activeSource === src) {{ activeSource = null; pill.classList.remove('active'); }}
        else {{
            document.querySelectorAll('.source-pill').forEach(p => p.classList.remove('active'));
            activeSource = src; pill.classList.add('active');
        }}
        filterRows();
    }});
}});

document.querySelectorAll('.type-pill').forEach(pill => {{
    pill.addEventListener('click', () => {{
        const t = pill.dataset.type;
        if (activeType === t) {{ activeType = null; pill.classList.remove('active'); }}
        else {{
            document.querySelectorAll('.type-pill').forEach(p => p.classList.remove('active'));
            activeType = t; pill.classList.add('active');
        }}
        filterRows();
    }});
}});

// Column sorting
document.querySelectorAll('th[data-sort]').forEach(th => {{
    th.addEventListener('click', () => {{
        const key = th.dataset.sort;
        const tbody = document.querySelector('#rfp-table tbody');
        const arr = Array.from(rows);
        const dir = th.classList.contains('sort-asc') ? -1 : 1;
        document.querySelectorAll('th').forEach(t => t.classList.remove('sort-asc', 'sort-desc'));
        th.classList.add(dir === 1 ? 'sort-asc' : 'sort-desc');
        arr.sort((a, b) => {{
            const av = (a.dataset[key] || '').toLowerCase();
            const bv = (b.dataset[key] || '').toLowerCase();
            return av < bv ? -dir : av > bv ? dir : 0;
        }});
        arr.forEach(r => tbody.appendChild(r));
    }});
}});

updateCount();
</script>
</body>
</html>'''


def _render_rfp_row(r, is_new, now):
    source = r.get("source", "")
    title = r.get("title", "")
    url = r.get("url", "")
    sol_type = r.get("solicitation_type") or "other"
    due = r.get("due_date") or ""
    first_seen = r.get("first_seen") or ""

    type_color = TYPE_COLORS.get(sol_type, "#64748b")

    title_html = f'<a href="{e(url)}" target="_blank" rel="noopener">{e(title)}</a>' if url else e(title)
    new_html = '<span class="new-badge">NEW</span>' if is_new else ""

    due_cls = ""
    if due:
        try:
            due_dt = datetime.fromisoformat(due)
            days = (due_dt - now).days
            if days < 0:
                due_cls = "overdue"
            elif days <= 7:
                due_cls = "soon"
            elif days <= 14:
                due_cls = "upcoming"
        except ValueError:
            pass

    seen_short = ""
    if first_seen:
        try:
            seen_short = datetime.fromisoformat(first_seen).strftime("%m/%d")
        except ValueError:
            pass

    source_label = SOURCE_LABELS.get(source, source)

    return (
        f'<tr class="rfp-row {"is-new" if is_new else ""}" '
        f'data-source="{e(source)}" data-type="{e(sol_type)}" '
        f'data-title="{e(title.lower())}" data-due="{e(due)}" data-seen="{e(first_seen)}">'
        f'<td>{e(source_label)}</td>'
        f'<td><span class="type-badge" style="background:{type_color}">{e(sol_type)}</span></td>'
        f'<td class="rfp-title">{title_html}{new_html}</td>'
        f'<td class="due-date {due_cls} hide-mobile">{e(due)}</td>'
        f'<td class="dim hide-mobile">{e(seen_short)}</td>'
        f'</tr>'
    )


def e(text):
    """HTML-escape shorthand."""
    return escape(str(text)) if text else ""
