"""CLI interface for the Localizer RFP monitoring tool."""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from localizer.db import Database, DEFAULT_DB_PATH
from localizer.scrapers import SCRAPERS

console = Console()


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), help="Database path")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
@click.pass_context
def main(ctx, db_path, verbose):
    """Localizer: Portland-area government procurement monitor (RFP/RFI/RFQ/IFB and more)."""
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["db"] = Database(Path(db_path))


@main.command()
@click.argument("sources", nargs=-1)
@click.pass_context
def scrape(ctx, sources):
    """Run scrapers. Specify source names or omit for all.

    Sources: portland, multnomah, metro, trimet, port, oregonbuys
    """
    db = ctx.obj["db"]
    targets = sources if sources else SCRAPERS.keys()

    total_found = 0
    total_new = 0

    for name in targets:
        if name not in SCRAPERS:
            console.print(f"[red]Unknown source: {name}[/red]")
            console.print(f"Available: {', '.join(SCRAPERS.keys())}")
            continue

        scraper = SCRAPERS[name](db)
        console.print(f"[cyan]Scraping {name}...[/cyan]", end=" ")
        try:
            found, new = scraper.run()
            total_found += found
            total_new += new
            console.print(f"[green]{found} found, {new} new[/green]")
        except Exception as e:
            console.print(f"[red]FAILED: {e}[/red]")
        finally:
            scraper.close()

    console.print(f"\n[bold]Total: {total_found} solicitations found, {total_new} new[/bold]")


@main.command(name="list")
@click.option("--source", "-s", help="Filter by source")
@click.option("--all", "show_all", is_flag=True, help="Show all, not just open")
@click.pass_context
def list_rfps(ctx, source, show_all):
    """List open RFPs."""
    db = ctx.obj["db"]
    rfps = db.get_open_rfps(source=source) if not show_all else db.search("")

    if not rfps:
        console.print("[yellow]No RFPs found.[/yellow]")
        return

    _print_rfp_table(rfps)


@main.command()
@click.argument("query")
@click.pass_context
def search(ctx, query):
    """Search RFPs by keyword."""
    db = ctx.obj["db"]
    rfps = db.search(query)

    if not rfps:
        console.print(f"[yellow]No RFPs matching '{query}'[/yellow]")
        return

    _print_rfp_table(rfps)


@main.command()
@click.option("--days", "-d", default=1, help="Show RFPs from last N days")
@click.pass_context
def new(ctx, days):
    """Show newly discovered RFPs."""
    db = ctx.obj["db"]
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rfps = db.get_new_rfps(since=since)

    if not rfps:
        console.print(f"[yellow]No new RFPs in the last {days} day(s).[/yellow]")
        return

    console.print(f"[bold green]{len(rfps)} new RFP(s) in the last {days} day(s):[/bold green]\n")
    _print_rfp_table(rfps)


@main.command()
@click.option("--limit", "-n", default=20, help="Number of entries to show")
@click.pass_context
def history(ctx, limit):
    """Show scrape history."""
    db = ctx.obj["db"]
    entries = db.get_scrape_history(limit=limit)

    if not entries:
        console.print("[yellow]No scrape history.[/yellow]")
        return

    table = Table(title="Scrape History")
    table.add_column("Source", style="cyan")
    table.add_column("Status")
    table.add_column("Found", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Finished", style="dim")
    table.add_column("Error", style="red")

    for e in entries:
        status_style = "green" if e["status"] == "success" else "red"
        table.add_row(
            e["source"],
            f"[{status_style}]{e['status']}[/{status_style}]",
            str(e["rfps_found"]),
            str(e["rfps_new"]),
            e["finished_at"] or "",
            (e["error"] or "")[:50],
        )

    console.print(table)


@main.command()
@click.option("--email", "send_email", is_flag=True, help="Send digest via email")
@click.option("--no-mark", is_flag=True, help="Don't mark RFPs as notified")
@click.pass_context
def digest(ctx, send_email, no_mark):
    """Show unnotified RFPs as a digest, optionally send via email."""
    from localizer.digest import generate_digest

    db = ctx.obj["db"]
    text, html, rfps = generate_digest(db, mark_notified=not no_mark)

    if not rfps:
        console.print("[yellow]No new solicitations to report.[/yellow]")
        return

    console.print(f"[bold green]Digest: {len(rfps)} new opportunity(ies)[/bold green]\n")
    _print_rfp_table(rfps)

    if send_email:
        from localizer.email import send_digest_email
        count = len(rfps)
        subject = f"Localizer: {count} new procurement opportunit{'y' if count == 1 else 'ies'}"
        if send_digest_email(text, html, subject=subject):
            console.print("[green]Email sent successfully.[/green]")
        else:
            console.print("[red]Email delivery failed. Check LOCALIZER_SMTP_* env vars.[/red]")

    if not no_mark:
        console.print(f"[dim]Marked {len(rfps)} solicitations as notified.[/dim]")


@main.command()
@click.pass_context
def sources(ctx):
    """List available scraper sources."""
    table = Table(title="Available Sources")
    table.add_column("Name", style="cyan")
    table.add_column("Portal")
    table.add_column("URL", style="dim")

    portal_names = {
        "portland": "City of Portland (SAP Ariba)",
        "multnomah": "Multnomah County (JAGGAER)",
        "metro": "Oregon Metro (Bid Locker)",
        "trimet": "TriMet (JAGGAER)",
        "port": "Port of Portland (PlanetBids)",
        "oregonbuys": "OregonBuys (State of Oregon)",
    }

    for name, cls in SCRAPERS.items():
        table.add_row(name, portal_names.get(name, ""), cls.base_url)

    console.print(table)


def _print_rfp_table(rfps: list[dict]):
    table = Table(show_lines=True)
    table.add_column("Source", style="cyan", width=12)
    table.add_column("Type", width=6)
    table.add_column("Title", style="bold", max_width=50)
    table.add_column("Due Date", width=12)
    table.add_column("Category", width=15)
    table.add_column("URL", style="dim", max_width=40)

    for r in rfps:
        due = r.get("due_date") or ""
        # Highlight approaching deadlines
        due_style = ""
        if due:
            try:
                due_dt = datetime.fromisoformat(due)
                days_left = (due_dt - datetime.utcnow()).days
                if days_left < 0:
                    due_style = "red strikethrough"
                elif days_left <= 7:
                    due_style = "red bold"
                elif days_left <= 14:
                    due_style = "yellow"
            except ValueError:
                pass

        sol_type = r.get("solicitation_type") or "other"
        type_style = {
            "RFP": "bold green", "RFI": "bold blue", "RFQ": "bold magenta",
            "IFB": "bold yellow", "ITB": "bold yellow",
        }.get(sol_type, "dim")

        table.add_row(
            r.get("source", ""),
            f"[{type_style}]{sol_type}[/{type_style}]",
            r.get("title", ""),
            f"[{due_style}]{due}[/{due_style}]" if due_style else due,
            r.get("category") or "",
            r.get("url") or "",
        )

    console.print(table)


if __name__ == "__main__":
    main()
