"""Static HTML dashboard generator.

Reads the SQLite database, scores every opportunity, and generates a static
site with priority tiers, clickable links, and content previews.
"""

import json
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from localizer.db import Database
from localizer.scoring import score_rfps, ScoredRFP


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

PRIORITY_COLORS = {
    "high": "#059669", "medium": "#d97706", "low": "#64748b", "excluded": "#dc2626",
}


def generate_site(db: Database, output_dir: Path):
    """Generate a complete static site from the database."""
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rfps = db.get_open_rfps()
    now = datetime.utcnow()
    since_7d = (now - timedelta(days=7)).isoformat()
    new_rfps = db.get_new_rfps(since=since_7d)
    history = db.get_scrape_history(limit=50)

    # Score everything
    scored = score_rfps(all_rfps)
    new_ids = {r["id"] for r in new_rfps}

    # Count by tier
    high = [s for s in scored if s.priority == "high"]
    medium = [s for s in scored if s.priority == "medium"]
    low = [s for s in scored if s.priority == "low"]
    excluded = [s for s in scored if s.priority == "excluded"]
    visible = [s for s in scored if s.priority != "excluded"]

    html = _render_page(scored, new_ids, high, medium, low, excluded, history, now)
    (output_dir / "index.html").write_text(html)

    # JSON export (non-excluded only, with scores)
    export = []
    for s in visible:
        r = dict(s.rfp)
        r["relevance_score"] = s.score
        r["priority"] = s.priority
        r["matched_keywords"] = s.matched_keywords
        export.append(r)
    (output_dir / "data.json").write_text(json.dumps(export, indent=2, default=str))

    (output_dir / "_redirects").write_text("/* /index.html 200\n")
    return len(visible)


def _render_page(scored, new_ids, high, medium, low, excluded, history, now):
    now_str = now.strftime("%B %d, %Y at %H:%M UTC")
    visible = [s for s in scored if s.priority != "excluded"]

    # Build cards for each visible opportunity
    cards_html = []
    for s in visible:
        cards_html.append(_render_card(s, s.rfp["id"] in new_ids, now))

    # Closing soon
    upcoming = []
    for s in visible:
        due = s.rfp.get("due_date")
        if due:
            try:
                days = (datetime.fromisoformat(due) - now).days
                if 0 <= days <= 7:
                    upcoming.append((s, days))
            except ValueError:
                pass
    upcoming.sort(key=lambda x: x[1])

    upcoming_html = ""
    if upcoming:
        items = []
        for s, days in upcoming[:5]:
            r = s.rfp
            label = "TODAY" if days == 0 else f"{days}d"
            url = r.get("url") or ""
            title = r.get("title", "")[:60]
            title_el = f'<a href="{e(url)}" target="_blank">{e(title)}</a>' if url else e(title)
            items.append(
                f'<div class="deadline-item">'
                f'<span class="deadline-days {"urgent" if days <= 2 else ""}">{label}</span>'
                f'<span class="deadline-title">{title_el}</span>'
                f'<span class="deadline-source">{e(SOURCE_LABELS.get(r.get("source",""), r.get("source","")))}</span>'
                f'</div>'
            )
        upcoming_html = f'''
        <div class="card deadline-card">
            <h2>Closing Soon</h2>
            {"".join(items)}
        </div>'''

    # History
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
            f'<tr><td>{e(SOURCE_LABELS.get(h["source"], h["source"]))}</td>'
            f'<td class="status-{status_cls}">{e(h["status"])}</td>'
            f'<td>{h["rfps_found"]}</td><td>{h["rfps_new"]}</td>'
            f'<td class="dim">{e(finished)}</td></tr>'
        )

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Localizer — Portland Procurement Monitor</title>
<style>
:root {{
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #e2e8f0; --text-dim: #94a3b8; --accent: #38bdf8;
    --green: #34d399; --red: #f87171; --yellow: #fbbf24; --orange: #fb923c;
    --border: #475569;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
}}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.container {{ max-width: 1000px; margin: 0 auto; padding: 20px; }}
header {{
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 20px 0; margin-bottom: 24px;
}}
header .container {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
h1 {{ font-size: 1.5rem; font-weight: 700; }}
h1 span {{ color: var(--accent); }}
.updated {{ color: var(--text-dim); font-size: 0.85rem; }}

/* Stats */
.stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
.stat {{ background: var(--surface); border-radius: 8px; padding: 14px 18px; flex: 1; min-width: 120px; }}
.stat-value {{ font-size: 1.8rem; font-weight: 700; }}
.stat-label {{ color: var(--text-dim); font-size: 0.8rem; }}

/* Filters */
.filters {{
    display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; align-items: center;
}}
.search-box {{
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 8px 14px; border-radius: 6px; font-size: 0.9rem; width: 280px;
}}
.search-box::placeholder {{ color: var(--text-dim); }}
.pill {{
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-size: 0.8rem; cursor: pointer; color: white;
    background: var(--surface2); transition: all 0.15s; user-select: none; border: none;
}}
.pill:hover {{ opacity: 0.85; }}
.pill.active {{ box-shadow: 0 0 0 2px var(--accent); }}
.pill strong {{ margin-left: 4px; }}
#rfp-count {{ color: var(--text-dim); font-size: 0.85rem; margin-bottom: 12px; }}

/* Deadline card */
.card {{ background: var(--surface); border-radius: 8px; padding: 20px; margin-bottom: 20px; border: 1px solid var(--border); }}
.card h2 {{ font-size: 1rem; margin-bottom: 10px; color: var(--text-dim); }}
.deadline-card {{ border-left: 3px solid var(--yellow); }}
.deadline-item {{ display: flex; align-items: center; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--border); }}
.deadline-item:last-child {{ border-bottom: none; }}
.deadline-days {{ background: var(--yellow); color: #000; font-weight: 700; font-size: 0.8rem; padding: 2px 8px; border-radius: 4px; min-width: 48px; text-align: center; }}
.deadline-days.urgent {{ background: var(--red); color: white; }}
.deadline-title {{ flex: 1; }}
.deadline-source {{ color: var(--text-dim); font-size: 0.85rem; }}

/* Opportunity cards */
.opp-card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 16px 20px; margin-bottom: 12px; transition: border-color 0.15s;
    border-left: 4px solid var(--border);
}}
.opp-card:hover {{ border-color: var(--accent); }}
.opp-card.priority-high {{ border-left-color: var(--green); }}
.opp-card.priority-medium {{ border-left-color: var(--orange); }}
.opp-card.priority-low {{ border-left-color: var(--surface2); }}
.opp-card.is-new {{ background: #1a2e1a; }}
.opp-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 6px; }}
.opp-title {{ font-size: 1rem; font-weight: 600; flex: 1; }}
.opp-title a {{ color: var(--text); }}
.opp-title a:hover {{ color: var(--accent); }}
.opp-score {{
    font-size: 0.8rem; font-weight: 700; padding: 2px 8px; border-radius: 4px;
    white-space: nowrap; flex-shrink: 0;
}}
.score-high {{ background: #065f46; color: var(--green); }}
.score-medium {{ background: #78350f; color: var(--orange); }}
.score-low {{ background: var(--surface2); color: var(--text-dim); }}
.opp-badges {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }}
.badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 0.7rem; font-weight: 700; color: white;
}}
.badge-new {{ background: var(--green); color: #000; }}
.opp-meta {{ color: var(--text-dim); font-size: 0.85rem; margin-bottom: 4px; }}
.opp-meta strong {{ color: var(--text); }}
.opp-description {{ color: var(--text-dim); font-size: 0.85rem; margin-top: 6px; line-height: 1.4; }}
.opp-keywords {{ font-size: 0.8rem; color: var(--green); margin-top: 6px; }}
.opp-link {{
    display: inline-block; margin-top: 8px; padding: 6px 14px; background: var(--accent);
    color: #0f172a; border-radius: 6px; font-size: 0.85rem; font-weight: 600;
    text-decoration: none;
}}
.opp-link:hover {{ opacity: 0.9; text-decoration: none; }}

/* Misc */
.dim {{ color: var(--text-dim); }}
.status-success {{ color: var(--green); }}
.status-error {{ color: var(--red); }}
.history-table {{ margin-top: 24px; }}
.history-table table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
.history-table th, .history-table td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); text-align: left; }}
.history-table th {{ color: var(--text-dim); font-size: 0.75rem; text-transform: uppercase; }}
.empty-state {{ text-align: center; padding: 60px 20px; color: var(--text-dim); }}
.excluded-count {{ color: var(--text-dim); font-size: 0.85rem; margin-bottom: 20px; }}
@media (max-width: 768px) {{
    .container {{ padding: 12px; }}
    .stats {{ gap: 8px; }}
    .stat {{ min-width: 80px; padding: 10px; }}
    .stat-value {{ font-size: 1.3rem; }}
    .search-box {{ width: 100%; }}
    .opp-header {{ flex-direction: column; gap: 4px; }}
    .opp-link {{ display: block; text-align: center; }}
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
            <div class="stat-value" style="color: var(--green)">{len(high)}</div>
            <div class="stat-label">High Priority</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color: var(--orange)">{len(medium)}</div>
            <div class="stat-label">Medium Priority</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(low)}</div>
            <div class="stat-label">Low Priority</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color: var(--yellow)">{len(upcoming)}</div>
            <div class="stat-label">Closing This Week</div>
        </div>
    </div>

    {upcoming_html}

    <div class="filters">
        <input type="text" class="search-box" id="search" placeholder="Search opportunities...">
        <button class="pill priority-pill active" data-priority="high" style="background: #065f46; color: var(--green)">High <strong>{len(high)}</strong></button>
        <button class="pill priority-pill active" data-priority="medium" style="background: #78350f; color: var(--orange)">Med <strong>{len(medium)}</strong></button>
        <button class="pill priority-pill" data-priority="low" style="background: var(--surface2)">Low <strong>{len(low)}</strong></button>
    </div>
    <div id="rfp-count"></div>

    <div id="cards-container">
        {"".join(cards_html) if cards_html else '<div class="empty-state"><h2>No opportunities yet</h2><p>Scraper has not run yet. Trigger a manual run in GitHub Actions.</p></div>'}
    </div>

    <div class="excluded-count">{len(excluded)} excluded (construction, janitorial, IFB/ITB, etc.)</div>

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
const cards = document.querySelectorAll('.opp-card');
const search = document.getElementById('search');
const countEl = document.getElementById('rfp-count');
let activePriorities = new Set(['high', 'medium']);

function updateCount() {{
    const visible = document.querySelectorAll('.opp-card:not([style*="display: none"])').length;
    countEl.textContent = `Showing ${{visible}} of ${{cards.length}} opportunities`;
}}

function filterCards() {{
    const q = search.value.toLowerCase();
    cards.forEach(card => {{
        const text = card.textContent.toLowerCase();
        const pri = card.dataset.priority;
        const matchSearch = !q || text.includes(q);
        const matchPriority = activePriorities.size === 0 || activePriorities.has(pri);
        card.style.display = (matchSearch && matchPriority) ? '' : 'none';
    }});
    updateCount();
}}

search.addEventListener('input', filterCards);

document.querySelectorAll('.priority-pill').forEach(pill => {{
    pill.addEventListener('click', () => {{
        const pri = pill.dataset.priority;
        if (activePriorities.has(pri)) {{
            activePriorities.delete(pri);
            pill.classList.remove('active');
        }} else {{
            activePriorities.add(pri);
            pill.classList.add('active');
        }}
        filterCards();
    }});
}});

updateCount();
// Start with high+medium visible
filterCards();
</script>
</body>
</html>'''


def _render_card(s: ScoredRFP, is_new: bool, now: datetime) -> str:
    r = s.rfp
    source = r.get("source", "")
    title = r.get("title", "")
    url = r.get("url") or ""
    sol_type = r.get("solicitation_type") or "other"
    due = r.get("due_date") or ""
    desc = r.get("description") or ""
    category = r.get("category") or ""
    value = r.get("estimated_value") or ""
    first_seen = r.get("first_seen") or ""

    source_label = SOURCE_LABELS.get(source, source)
    type_color = TYPE_COLORS.get(sol_type, "#64748b")

    # Title with link
    if url:
        title_html = f'<a href="{e(url)}" target="_blank" rel="noopener">{e(title)}</a>'
    else:
        title_html = e(title)

    # Score styling
    score_cls = f"score-{s.priority}"

    # Badges
    badges = []
    if is_new:
        badges.append('<span class="badge badge-new">NEW</span>')
    badges.append(f'<span class="badge" style="background:{e(type_color)}">{e(sol_type)}</span>')
    badges.append(f'<span class="badge" style="background:#0066cc">{e(source_label)}</span>')

    # Due date
    due_html = ""
    if due:
        due_display = due
        try:
            due_dt = datetime.fromisoformat(due)
            days = (due_dt - now).days
            if days < 0:
                due_display = f"{due} (closed)"
            elif days == 0:
                due_display = f"{due} (TODAY)"
            elif days <= 7:
                due_display = f"{due} ({days} days left)"
        except ValueError:
            pass
        due_html = f'<strong>Due:</strong> {e(due_display)}'

    # Meta line
    meta_parts = []
    if due_html:
        meta_parts.append(due_html)
    if category:
        meta_parts.append(f"<strong>Category:</strong> {e(category)}")
    if value:
        meta_parts.append(f"<strong>Value:</strong> {e(value)}")
    if first_seen:
        try:
            seen = datetime.fromisoformat(first_seen).strftime("%b %d")
            meta_parts.append(f"Found {e(seen)}")
        except ValueError:
            pass
    meta_html = " &bull; ".join(meta_parts) if meta_parts else ""

    # Description preview
    desc_html = ""
    if desc:
        preview = desc[:250]
        if len(desc) > 250:
            preview += "..."
        desc_html = f'<div class="opp-description">{e(preview)}</div>'

    # Keywords
    kw_html = ""
    if s.matched_keywords:
        kw_html = f'<div class="opp-keywords">Matched: {e(", ".join(s.matched_keywords))}</div>'

    # Link button
    link_html = ""
    if url:
        link_html = f'<a href="{e(url)}" target="_blank" rel="noopener" class="opp-link">View Solicitation &rarr;</a>'

    new_cls = "is-new" if is_new else ""
    badges_html = "".join(badges)
    meta_div = f'<div class="opp-meta">{meta_html}</div>' if meta_html else ""

    return (
        f'<div class="opp-card priority-{s.priority} {new_cls}" '
        f'data-priority="{e(s.priority)}" data-source="{e(source)}" data-score="{s.score}">'
        f'<div class="opp-header">'
        f'<div class="opp-title">{title_html}</div>'
        f'<span class="opp-score {score_cls}">{s.score}/100</span>'
        f'</div>'
        f'<div class="opp-badges">{badges_html}</div>'
        f'{meta_div}'
        f'{desc_html}'
        f'{kw_html}'
        f'{link_html}'
        f'</div>'
    )


def e(text):
    """HTML-escape shorthand."""
    return escape(str(text)) if text else ""
