"""JavLibrary.com scraper module.

JavLibrary structure:
  - Search: /en/vl_searchbyid.php?keyword={id}
  - Movie detail: /en/?v={code}
  - Uses old-school HTML tables with specific IDs:
    #video_id, #video_title, #video_date, #video_length,
    #video_director, #video_maker, #video_label, #video_genres,
    #video_cast, etc.
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from ..models import JAVMovie, Performer, SearchResult
from .base import BaseScraper

logger = logging.getLogger(__name__)


class JavLibraryScraper(BaseScraper):
    SOURCE_NAME = "javlibrary"
    BASE_URL = "https://www.javlibrary.com"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cookies.setdefault("over18", "18")

    def _build_headers(self) -> dict:
        headers = super()._build_headers()
        headers["Referer"] = f"{self.BASE_URL}/en/"
        return headers

    # ── Search ───────────────────────────────────────────────────

    async def search(self, query: str) -> list[SearchResult]:
        """Search JavLibrary for a JAV ID."""
        url = f"{self.BASE_URL}/en/vl_searchbyid.php?keyword={query}"
        results: list[SearchResult] = []
        try:
            html = await self.fetch(url)
            tree = self.parse_html(html)

            # Check if we landed directly on a video page
            if tree.css_first("#video_id"):
                movie = self._parse_detail(html, url)
                if movie:
                    results.append(SearchResult(
                        dvd_id=movie.dvd_id,
                        title=movie.title,
                        cover_url=movie.cover_url,
                        release_date=movie.release_date,
                        performers=[p.name for p in movie.performers],
                        detail_url=url,
                        source=self.SOURCE_NAME,
                    ))
                return results

            # Multiple results - parse search result list
            items = tree.css(".video, .videothumblist .video, div.video")
            for item in items:
                link = item.css_first("a")
                if not link:
                    continue

                href = self.attr(link, "href")
                detail_url = self.abs_url(href)

                # Title from div.id
                id_node = item.css_first("div.id, .id")
                dvd_id = self.text(id_node, query)

                title_node = item.css_first("div.title, .title")
                title = self.text(title_node)

                # Cover
                img = item.css_first("img")
                cover = self.attr(img, "src") or self.attr(img, "data-src")
                if cover:
                    cover = self.abs_url(cover)

                results.append(SearchResult(
                    dvd_id=self.normalize_id(dvd_id),
                    title=self.clean_text(title),
                    cover_url=cover,
                    detail_url=detail_url,
                    source=self.SOURCE_NAME,
                ))

        except Exception as e:
            logger.warning(f"JavLibrary search failed for '{query}': {e}")

        return results

    # ── Movie detail ─────────────────────────────────────────────

    async def get_movie(self, dvd_id: str) -> Optional[JAVMovie]:
        results = await self.search(dvd_id)
        if not results:
            logger.info(f"JavLibrary: no results for {dvd_id}")
            return None

        norm = self.normalize_id(dvd_id)
        target = None
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
        try:
            html = await self.fetch(url)
            return self._parse_detail(html, url)
        except Exception as e:
            logger.error(f"JavLibrary detail scrape failed for {url}: {e}")
            return None

    def _parse_detail(self, html: str, url: str) -> Optional[JAVMovie]:
        tree = self.parse_html(html)
        movie = JAVMovie()
        movie.source_urls[self.SOURCE_NAME] = url

        # DVD ID - #video_id .text
        vid_id = tree.css_first("#video_id .text, #video_id td.text")
        movie.dvd_id = self.normalize_id(self.text(vid_id))

        # Title - #video_title a or h3
        title_node = tree.css_first("#video_title a, #video_title h3, h3.post-title")
        movie.title = self.clean_text(self.text(title_node))

        # Release date
        date_node = tree.css_first("#video_date .text, #video_date td.text")
        movie.release_date = self.clean_text(self.text(date_node))

        # Runtime
        length_node = tree.css_first("#video_length .text, #video_length span.text")
        runtime_val = self.clean_text(self.text(length_node))
        if runtime_val:
            movie.runtime = f"{runtime_val} min."

        # Director
        director_node = tree.css_first("#video_director .text a, #video_director td.text a")
        movie.director = self.clean_text(self.text(director_node))

        # Studio / Maker
        maker_node = tree.css_first("#video_maker .text a, #video_maker td.text a")
        movie.maker = self.clean_text(self.text(maker_node))
        movie.studio = movie.maker

        # Label
        label_node = tree.css_first("#video_label .text a, #video_label td.text a")
        movie.label = self.clean_text(self.text(label_node))

        # Cover image
        cover_node = tree.css_first("#video_jacket img, #video_jacket_img")
        if cover_node:
            cover_src = self.attr(cover_node, "src")
            if cover_src:
                movie.cover_url = self.abs_url(cover_src)

        # Genres
        genre_nodes = tree.css("#video_genres .genre a, #video_genres span.genre a")
        for g in genre_nodes:
            genre_text = self.clean_text(self.text(g))
            if genre_text and genre_text not in movie.genres:
                movie.genres.append(genre_text)

        # Performers / Cast
        cast_nodes = tree.css("#video_cast .cast a.star, #video_cast span.star a")
        for actor in cast_nodes:
            name = self.clean_text(self.text(actor))
            if name and name != "----":
                movie.performers.append(Performer(
                    name=name,
                    profile_url=self.abs_url(self.attr(actor, "href")),
                    source=self.SOURCE_NAME,
                ))

        # Rating
        rating_node = tree.css_first("#video_review .score .text, span.score")
        rating_text = self.text(rating_node)
        if rating_text:
            try:
                m = re.search(r"[\d.]+", rating_text)
                if m:
                    movie.rating = float(m.group())
            except ValueError:
                pass

        # Screenshots from review section or sample images
        sample_nodes = tree.css(".previewthumbs img, a.sample img")
        for img in sample_nodes:
            src = self.attr(img, "src") or self.attr(img, "data-src")
            if src:
                full_src = self.abs_url(src)
                if full_src not in movie.screenshot_urls:
                    movie.screenshot_urls.append(full_src)

        return movie if movie.dvd_id else None
