#!/usr/bin/env python3
"""CLI interface for the JAV Ultimate Scraper.

Usage:
    python -m javdb SSIS-001
    python -m javdb --url https://javdb.com/v/96pOBq
    python -m javdb --search "Eimi Fukada"
    python -m javdb --performer "Eimi Fukada"
    python -m javdb CJOD-523 --sources javdatabase
    python -m javdb CJOD-523 --json
    python -m javdb CJOD-523 --output result.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .api import JAVScraper
from .models import ScrapeResult, JAVMovie

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="javdb",
        description="JAV Ultimate Scraper - Multi-source JAV metadata aggregator",
    )
    parser.add_argument(
        "dvd_id",
        nargs="?",
        help="JAV DVD ID to scrape (e.g., SSIS-001, CJOD-523)",
    )
    parser.add_argument(
        "--url",
        help="Scrape a specific URL instead of searching by ID",
    )
    parser.add_argument(
        "--search",
        help="Search for movies by keyword",
    )
    parser.add_argument(
        "--performer", "--idol",
        help="Look up a performer/idol profile",
    )
    parser.add_argument(
        "--sources",
        default="javdb,javlibrary,javdatabase",
        help="Comma-separated list of sources (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw JSON",
    )
    parser.add_argument(
        "--output", "-o",
        help="Write JSON output to a file",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--proxy",
        help="HTTP/SOCKS proxy URL",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    return parser


def display_movie(movie: JAVMovie, result: ScrapeResult):
    """Display a movie in a rich formatted table."""

    # Header
    title_text = f"{movie.dvd_id}"
    if movie.title:
        title_text += f" - {movie.title}"

    # Main info table
    table = Table(
        show_header=False,
        box=box.ROUNDED,
        title=title_text,
        title_style="bold cyan",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Field", style="bold yellow", width=16)
    table.add_column("Value", style="white")

    def add_row(label: str, value: Optional[str]):
        if value:
            table.add_row(label, value)

    add_row("DVD ID", movie.dvd_id)
    add_row("Content ID", movie.content_id)
    add_row("Title", movie.title)
    add_row("Title (JP)", movie.title_jp)
    add_row("Release Date", movie.release_date)
    add_row("Runtime", movie.runtime)
    add_row("Studio", movie.studio)
    add_row("Maker", movie.maker)
    add_row("Label", movie.label)
    add_row("Series", movie.series)
    add_row("Director", movie.director)

    if movie.rating is not None:
        rating_str = f"{movie.rating}"
        if movie.rating_count:
            rating_str += f" ({movie.rating_count} votes)"
        add_row("Rating", rating_str)

    if movie.genres:
        add_row("Genres", ", ".join(movie.genres))

    if movie.performers:
        names = [p.name for p in movie.performers]
        add_row("Performers", ", ".join(names))

    add_row("Cover URL", movie.cover_url)
    add_row("Thumbnail", movie.thumbnail_url)
    add_row("Trailer", movie.trailer_url)

    if movie.screenshot_urls:
        add_row("Screenshots", f"{len(movie.screenshot_urls)} images")
        for i, url in enumerate(movie.screenshot_urls[:5], 1):
            add_row(f"  #{i}", url)
        if len(movie.screenshot_urls) > 5:
            add_row("  ...", f"+{len(movie.screenshot_urls) - 5} more")

    # Source URLs
    if movie.source_urls:
        add_row("Sources", "")
        for source, url in movie.source_urls.items():
            add_row(f"  {source}", url)

    console.print()
    console.print(table)

    # Performer details if available
    if movie.performers:
        for p in movie.performers:
            if p.age or p.measurements or p.cup_size:
                ptable = Table(
                    show_header=False,
                    box=box.SIMPLE,
                    title=f"Performer: {p.name}",
                    title_style="bold magenta",
                    padding=(0, 1),
                )
                ptable.add_column("Field", style="bold", width=16)
                ptable.add_column("Value")

                if p.name_jp:
                    ptable.add_row("Name (JP)", p.name_jp)
                if p.age:
                    ptable.add_row("Age", str(p.age))
                if p.dob:
                    ptable.add_row("DOB", p.dob)
                if p.height:
                    ptable.add_row("Height", p.height)
                if p.measurements:
                    ptable.add_row("Measurements", p.measurements)
                if p.cup_size:
                    ptable.add_row("Cup", p.cup_size)
                if p.birthplace:
                    ptable.add_row("Birthplace", p.birthplace)
                if p.twitter:
                    ptable.add_row("Twitter", p.twitter)
                if p.tags:
                    ptable.add_row("Tags", ", ".join(p.tags))

                console.print(ptable)

    # Status footer
    status_parts = []
    if result.sources_scraped:
        status_parts.append(f"[green]OK:[/green] {', '.join(result.sources_scraped)}")
    if result.sources_failed:
        status_parts.append(f"[red]Failed:[/red] {', '.join(result.sources_failed)}")
    console.print(f"\n  Sources: {' | '.join(status_parts)}")
    console.print()


def display_search_results(results):
    """Display search results in a table."""
    table = Table(
        title="Search Results",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("DVD ID", style="bold cyan")
    table.add_column("Title", max_width=50)
    table.add_column("Date", width=12)
    table.add_column("Source", style="yellow")

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r.dvd_id,
            (r.title or "")[:50],
            r.release_date or "",
            r.source,
        )

    console.print()
    console.print(table)
    console.print(f"\n  Total: {len(results)} results\n")


def display_performer(performer):
    """Display performer details."""
    table = Table(
        show_header=False,
        box=box.ROUNDED,
        title=f"Performer: {performer.name}",
        title_style="bold magenta",
        expand=True,
    )
    table.add_column("Field", style="bold yellow", width=16)
    table.add_column("Value")

    def add(label, value):
        if value:
            table.add_row(label, str(value))

    add("Name", performer.name)
    add("Name (JP)", performer.name_jp)
    add("Age", performer.age)
    add("DOB", performer.dob)
    add("Debut", performer.debut_date)
    add("Height", performer.height)
    add("Measurements", performer.measurements)
    add("Cup", performer.cup_size)
    add("Birthplace", performer.birthplace)
    add("Hair Color", performer.hair_color)
    add("Hair Length", performer.hair_length)
    add("Twitter", performer.twitter)
    add("Image", performer.image_url)
    add("Profile URL", performer.profile_url)

    if performer.tags:
        add("Tags", ", ".join(performer.tags))

    console.print()
    console.print(table)
    console.print()


async def run(args):
    sources = [s.strip() for s in args.sources.split(",")]

    async with JAVScraper(
        sources=sources,
        timeout=args.timeout,
        proxy=args.proxy,
    ) as scraper:

        # ── Search mode ──────────────────────────────────────────
        if args.search:
            results = await scraper.search(args.search)
            if args.json_output or args.output:
                data = [r.model_dump() for r in results]
                json_str = json.dumps(data, indent=2, ensure_ascii=False)
                if args.output:
                    with open(args.output, "w") as f:
                        f.write(json_str)
                    console.print(f"[green]Saved to {args.output}[/green]")
                else:
                    print(json_str)
            else:
                if results:
                    display_search_results(results)
                else:
                    console.print("[red]No results found.[/red]")
            return

        # ── Performer lookup ─────────────────────────────────────
        if args.performer:
            performer = await scraper.get_performer(args.performer)
            if performer:
                if args.json_output or args.output:
                    json_str = performer.model_dump_json(indent=2)
                    if args.output:
                        with open(args.output, "w") as f:
                            f.write(json_str)
                        console.print(f"[green]Saved to {args.output}[/green]")
                    else:
                        print(json_str)
                else:
                    display_performer(performer)
            else:
                console.print(f"[red]Performer '{args.performer}' not found.[/red]")
            return

        # ── URL scrape ───────────────────────────────────────────
        if args.url:
            result = await scraper.scrape_url(args.url)
        elif args.dvd_id:
            result = await scraper.scrape(args.dvd_id)
        else:
            console.print("[red]Please provide a DVD ID, --url, --search, or --performer.[/red]")
            console.print("Usage: python -m javdb SSIS-001")
            return

        # ── Output ───────────────────────────────────────────────
        if args.json_output or args.output:
            if result.movie:
                json_str = result.movie.model_dump_json(indent=2)
            else:
                json_str = result.model_dump_json(indent=2)

            if args.output:
                with open(args.output, "w") as f:
                    f.write(json_str)
                console.print(f"[green]Saved to {args.output}[/green]")
            else:
                print(json_str)
        else:
            if result.success and result.movie:
                display_movie(result.movie, result)
            else:
                console.print(f"[red]Scrape failed.[/red]")
                for err in result.errors:
                    console.print(f"  [dim]{err}[/dim]")
                if result.sources_failed:
                    console.print(f"  Failed sources: {', '.join(result.sources_failed)}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()
