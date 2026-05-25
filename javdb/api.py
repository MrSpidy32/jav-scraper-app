"""Unified JAV Scraper API - the main entry point.

Usage:
    import asyncio
    from javdb.api import JAVScraper

    async def main():
        async with JAVScraper() as scraper:
            result = await scraper.scrape("SSIS-001")
            print(result.model_dump_json(indent=2))

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .models import JAVMovie, Performer, SearchResult, ScrapeResult
from .merger import merge_movies
from .scrapers.javdb_scraper import JavDBScraper
from .scrapers.javlibrary_scraper import JavLibraryScraper
from .scrapers.javdatabase_scraper import JavDatabaseScraper

logger = logging.getLogger(__name__)


class JAVScraper:
    """Multi-source JAV metadata scraper.

    Scrapes javdb.com, javlibrary.com, and javdatabase.com concurrently,
    then merges the results into a single unified JAVMovie object.

    Args:
        sources: List of source names to enable.
                 Default: ["javdb", "javlibrary", "javdatabase"]
        timeout: HTTP request timeout in seconds.
        proxy: Optional HTTP/SOCKS proxy URL.
        javdb_cookies: Extra cookies for javdb.com (e.g. session tokens).
        javlibrary_cookies: Extra cookies for javlibrary.com.
    """

    ALL_SOURCES = ["javdb", "javlibrary", "javdatabase"]

    def __init__(
        self,
        sources: Optional[list[str]] = None,
        timeout: float = 30.0,
        proxy: Optional[str] = None,
        javdb_cookies: Optional[dict] = None,
        javlibrary_cookies: Optional[dict] = None,
    ):
        self.enabled_sources = sources or self.ALL_SOURCES
        self.timeout = timeout
        self.proxy = proxy

        self._scrapers: dict[str, object] = {}

        if "javdb" in self.enabled_sources:
            self._scrapers["javdb"] = JavDBScraper(
                timeout=timeout,
                proxy=proxy,
                cookies=javdb_cookies or {},
            )
        if "javlibrary" in self.enabled_sources:
            self._scrapers["javlibrary"] = JavLibraryScraper(
                timeout=timeout,
                proxy=proxy,
                cookies=javlibrary_cookies or {},
            )
        if "javdatabase" in self.enabled_sources:
            self._scrapers["javdatabase"] = JavDatabaseScraper(
                timeout=timeout,
                proxy=proxy,
            )

    # ── Main API ─────────────────────────────────────────────────

    async def scrape(self, dvd_id: str) -> ScrapeResult:
        """Scrape a JAV movie by DVD ID from all enabled sources.

        Runs all scrapers concurrently, merges results, and returns
        a ScrapeResult with the unified movie data.
        """
        result = ScrapeResult()
        movies: list[JAVMovie] = []

        # Run all scrapers concurrently
        tasks = {}
        for name, scraper in self._scrapers.items():
            tasks[name] = asyncio.create_task(
                self._safe_scrape(name, scraper, dvd_id)
            )

        for name, task in tasks.items():
            movie = await task
            if movie:
                movies.append(movie)
                result.sources_scraped.append(name)
            else:
                result.sources_failed.append(name)

        if movies:
            result.movie = merge_movies(movies)
            result.success = True
        else:
            result.success = False
            result.errors.append(f"No sources returned data for '{dvd_id}'")

        return result

    async def scrape_url(self, url: str) -> ScrapeResult:
        """Scrape a specific URL from the appropriate source."""
        result = ScrapeResult()

        # Detect which scraper to use from URL
        scraper = None
        source_name = ""
        if "javdb.com" in url:
            scraper = self._scrapers.get("javdb")
            source_name = "javdb"
        elif "javlibrary.com" in url:
            scraper = self._scrapers.get("javlibrary")
            source_name = "javlibrary"
        elif "javdatabase.com" in url:
            scraper = self._scrapers.get("javdatabase")
            source_name = "javdatabase"

        if not scraper:
            result.success = False
            result.errors.append(f"No scraper available for URL: {url}")
            return result

        try:
            movie = await scraper.get_movie_by_url(url)
            if movie:
                result.movie = movie
                result.sources_scraped.append(source_name)
                result.success = True
            else:
                result.success = False
                result.sources_failed.append(source_name)
                result.errors.append(f"Failed to extract data from {url}")
        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            result.sources_failed.append(source_name)

        return result

    async def search(self, query: str) -> list[SearchResult]:
        """Search across all enabled sources concurrently."""
        all_results: list[SearchResult] = []

        tasks = {}
        for name, scraper in self._scrapers.items():
            tasks[name] = asyncio.create_task(
                self._safe_search(name, scraper, query)
            )

        for name, task in tasks.items():
            results = await task
            all_results.extend(results)

        return all_results

    async def get_performer(self, name: str) -> Optional[Performer]:
        """Get performer details (currently from JavDatabase)."""
        jdb = self._scrapers.get("javdatabase")
        if jdb and isinstance(jdb, JavDatabaseScraper):
            return await jdb.get_performer(name)
        return None

    # ── Internals ────────────────────────────────────────────────

    async def _safe_scrape(self, name: str, scraper, dvd_id: str) -> Optional[JAVMovie]:
        try:
            logger.info(f"Scraping {name} for {dvd_id}...")
            movie = await scraper.get_movie(dvd_id)
            if movie:
                logger.info(f"  {name}: got data (title={movie.title})")
            else:
                logger.info(f"  {name}: no data")
            return movie
        except Exception as e:
            logger.warning(f"  {name}: error - {e}")
            return None

    async def _safe_search(self, name: str, scraper, query: str) -> list[SearchResult]:
        try:
            return await scraper.search(query)
        except Exception as e:
            logger.warning(f"Search on {name} failed: {e}")
            return []

    # ── Context manager ──────────────────────────────────────────

    async def close(self):
        for scraper in self._scrapers.values():
            try:
                await scraper.close()
            except Exception:
                pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# ── Synchronous convenience wrappers ─────────────────────────────

def scrape_sync(dvd_id: str, **kwargs) -> ScrapeResult:
    """Synchronous wrapper for JAVScraper.scrape()."""
    async def _run():
        async with JAVScraper(**kwargs) as s:
            return await s.scrape(dvd_id)
    return asyncio.run(_run())


def search_sync(query: str, **kwargs) -> list[SearchResult]:
    """Synchronous wrapper for JAVScraper.search()."""
    async def _run():
        async with JAVScraper(**kwargs) as s:
            return await s.search(query)
    return asyncio.run(_run())
