"""JavDB.com scraper module.

JavDB uses Cloudflare protection, so this scraper uses browser-like headers
and cookie handling. The site structure uses:
  - Search: /search?q={query}&f=all
  - Movie detail: /v/{slug}
  - HTML uses .movie-panel-info for metadata, .video-detail for details
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from ..models import JAVMovie, Performer, SearchResult
from .base import BaseScraper

logger = logging.getLogger(__name__)


class JavDBScraper(BaseScraper):
    SOURCE_NAME = "javdb"
    BASE_URL = "https://javdb.com"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # JavDB needs specific cookies; users can pass locale
        self.cookies.setdefault("locale", "en")
        self.cookies.setdefault("over18", "1")

    # ── Search ───────────────────────────────────────────────────

    async def search(self, query: str) -> list[SearchResult]:
        """Search JavDB for a JAV ID or keyword."""
        url = f"{self.BASE_URL}/search?q={query}&f=all"
        results: list[SearchResult] = []
        try:
            html = await self.fetch(url)
            tree = self.parse_html(html)

            # Search results are in .movie-list .item
            items = tree.css(".movie-list .item, .grid-item, .box")
            for item in items:
                link = item.css_first("a")
                if not link:
                    continue

                href = self.attr(link, "href")
                detail_url = self.abs_url(href) if href else ""

                # Title from the link or title tag
                title_node = item.css_first(".video-title, strong, .uid")
                title = self.text(title_node)

                # DVD ID from uid span
                uid_node = item.css_first(".uid, .video-title strong")
                dvd_id = self.text(uid_node, query)

                # Cover image
                img = item.css_first("img")
                cover = self.attr(img, "src") or self.attr(img, "data-src")

                # Date
                date_node = item.css_first(".meta, .has-text-grey-dark")
                release_date = self.text(date_node)

                results.append(SearchResult(
                    dvd_id=self.normalize_id(dvd_id) if dvd_id else query,
                    title=self.clean_text(title),
                    cover_url=cover if cover else None,
                    release_date=self.clean_text(release_date),
                    detail_url=detail_url,
                    source=self.SOURCE_NAME,
                ))

        except Exception as e:
            logger.warning(f"JavDB search failed for '{query}': {e}")

        return results

    # ── Movie detail ─────────────────────────────────────────────

    async def get_movie(self, dvd_id: str) -> Optional[JAVMovie]:
        """Search for a movie by ID and scrape the first result's detail page."""
        results = await self.search(dvd_id)
        if not results:
            logger.info(f"JavDB: no results for {dvd_id}")
            return None

        # Find exact match or use first result
        target = None
        norm = self.normalize_id(dvd_id)
        for r in results:
            if self.normalize_id(r.dvd_id) == norm:
                target = r
                break
        if target is None:
            target = results[0]

        if not target.detail_url:
            return None

        return await self.get_movie_by_url(target.detail_url)

    async def get_movie_by_url(self, url: str) -> Optional[JAVMovie]:
        """Scrape a JavDB movie detail page."""
        try:
            html = await self.fetch(url)
            return self._parse_detail(html, url)
        except Exception as e:
            logger.error(f"JavDB detail scrape failed for {url}: {e}")
            return None

    def _parse_detail(self, html: str, url: str) -> JAVMovie:
        tree = self.parse_html(html)
        movie = JAVMovie()
        movie.source_urls[self.SOURCE_NAME] = url

        # Title - h2.title or strong in first-panel
        title_node = tree.css_first("h2.title strong.current-title, h2.title .origin-title, h2.title strong")
        movie.title = self.clean_text(self.text(title_node))

        # Cover image
        cover_node = tree.css_first(".column-video-cover img, .video-cover img, img.video-cover")
        if cover_node:
            movie.cover_url = self.attr(cover_node, "src") or self.attr(cover_node, "data-src")

        # Info panel rows - these are in .movie-panel-info or .video-detail
        # JavDB uses <div class="panel-block"> with <strong> label + <span> value
        info_blocks = tree.css(".panel-block, .movie-panel-info .panel-block")
        for block in info_blocks:
            label_node = block.css_first("strong, .header")
            if not label_node:
                continue
            label = self.text(label_node).lower().strip().rstrip(":")

            value_node = block.css_first("span.value, .value, a")
            value = self.text(value_node)

            if "番號" in label or "id" in label or "dvd" in label:
                movie.dvd_id = self.normalize_id(value)
            elif "日期" in label or "date" in label or "release" in label:
                movie.release_date = self.clean_text(value)
            elif "時長" in label or "duration" in label or "runtime" in label:
                movie.runtime = self.clean_text(value)
            elif "導演" in label or "director" in label:
                movie.director = self.clean_text(value)
            elif "片商" in label or "maker" in label or "studio" in label:
                movie.studio = self.clean_text(value)
                movie.maker = movie.studio
            elif "發行" in label or "publisher" in label or "label" in label:
                movie.label = self.clean_text(value)
            elif "系列" in label or "series" in label:
                movie.series = self.clean_text(value)
            elif "評分" in label or "rating" in label or "score" in label:
                try:
                    score_text = re.search(r"[\d.]+", value)
                    if score_text:
                        movie.rating = float(score_text.group())
                except (ValueError, AttributeError):
                    pass

        # Genres / tags
        tag_nodes = tree.css(".panel-block:has(strong) a[href*='tags'], .panel-block a[href*='genre'], .tag-block a")
        for tag in tag_nodes:
            g = self.clean_text(self.text(tag))
            if g and g not in movie.genres:
                movie.genres.append(g)

        # Performers / actresses
        actor_nodes = tree.css("a[href*='actors'], a[href*='stars']")
        seen_names = set()
        for actor in actor_nodes:
            name = self.clean_text(self.text(actor))
            if name and name not in seen_names:
                seen_names.add(name)
                movie.performers.append(Performer(
                    name=name,
                    profile_url=self.abs_url(self.attr(actor, "href")),
                    source=self.SOURCE_NAME,
                ))

        # Screenshots
        screenshot_nodes = tree.css(".preview-images img, .screenshot img, .tile-images img")
        for img in screenshot_nodes:
            src = self.attr(img, "src") or self.attr(img, "data-src")
            if src and src not in movie.screenshot_urls:
                movie.screenshot_urls.append(src)

        # Trailer
        video_node = tree.css_first("video source, #preview-video source")
        if video_node:
            movie.trailer_url = self.attr(video_node, "src")

        # Fallback DVD ID from title or URL
        if not movie.dvd_id:
            # Try to extract from page title
            page_title = tree.css_first("title")
            if page_title:
                t = self.text(page_title)
                m = re.search(r"([A-Z]+-\d+)", t, re.IGNORECASE)
                if m:
                    movie.dvd_id = self.normalize_id(m.group(1))

        return movie
