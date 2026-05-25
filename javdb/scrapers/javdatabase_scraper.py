"""JavDatabase.com scraper module.

JavDatabase is a WordPress site using Bootstrap. Structure:
  - Search: /?s={query}&post_type=movies
  - Movie: /movies/{dvd-id-lowercase}/
  - Idol: /idols/{name-slug}/

Movie detail page uses a table with <b>Label:</b> value pattern:
  Title, DVD ID, Content ID, Release Date, Runtime, Studio, Director,
  Genre(s), Idol(s)/Actress(es), JAV Series

Cover images at: /covers/full/{prefix}/{content_id}pl.webp
Thumbnails at: /covers/thumb/{prefix}/{content_id}ps.webp
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from ..models import JAVMovie, Performer, SearchResult
from .base import BaseScraper

logger = logging.getLogger(__name__)


class JavDatabaseScraper(BaseScraper):
    SOURCE_NAME = "javdatabase"
    BASE_URL = "https://www.javdatabase.com"

    # ── Search ───────────────────────────────────────────────────

    async def search(self, query: str) -> list[SearchResult]:
        """Search JavDatabase for movies by ID or keyword."""
        # JavDatabase search URL
        url = f"{self.BASE_URL}/?s={query}&post_type=movies"
        results: list[SearchResult] = []
        try:
            html = await self.fetch(url)
            tree = self.parse_html(html)

            # Check if redirected to a single movie page
            entry_content = tree.css_first(".movietable, .entry-content .movietable")
            if entry_content:
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

            # Multiple search results
            items = tree.css("article, .entry-content a, .search-results .post")
            for item in items:
                link = item.css_first("a[href*='/movies/']")
                if not link:
                    link = item if item.tag == "a" else None
                if not link:
                    continue

                href = self.attr(link, "href")
                if "/movies/" not in href:
                    continue

                detail_url = self.abs_url(href)

                # Extract DVD ID from URL slug
                slug_match = re.search(r"/movies/([^/]+)/?", href)
                dvd_id = slug_match.group(1).upper() if slug_match else query

                title_node = link.css_first("h2, .entry-title, strong") or link
                title = self.clean_text(self.text(title_node))

                img = item.css_first("img") if item.tag != "a" else None
                cover = self.attr(img, "src") if img else None

                results.append(SearchResult(
                    dvd_id=self.normalize_id(dvd_id),
                    title=title,
                    cover_url=cover,
                    detail_url=detail_url,
                    source=self.SOURCE_NAME,
                ))

        except Exception as e:
            logger.warning(f"JavDatabase search failed for '{query}': {e}")

        return results

    # ── Direct URL construction ──────────────────────────────────

    def _build_movie_url(self, dvd_id: str) -> str:
        """Build a direct movie URL from a DVD ID."""
        slug = dvd_id.lower().strip()
        return f"{self.BASE_URL}/movies/{slug}/"

    # ── Movie detail ─────────────────────────────────────────────

    async def get_movie(self, dvd_id: str) -> Optional[JAVMovie]:
        """Try direct URL first, fall back to search."""
        # Try direct URL first (faster)
        direct_url = self._build_movie_url(dvd_id)
        try:
            html = await self.fetch(direct_url)
            tree = self.parse_html(html)
            # Verify we got a movie page
            if tree.css_first(".movietable, .entry-content"):
                movie = self._parse_detail(html, direct_url)
                if movie and movie.dvd_id:
                    return movie
        except Exception:
            pass

        # Fall back to search
        results = await self.search(dvd_id)
        if not results:
            logger.info(f"JavDatabase: no results for {dvd_id}")
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
            logger.error(f"JavDatabase detail scrape failed for {url}: {e}")
            return None

    def _parse_detail(self, html: str, url: str) -> Optional[JAVMovie]:
        """Parse a JavDatabase movie detail page.

        The page uses a pattern of <p><b>Label:</b> value</p> inside a
        .col-md-10 div, with cover image in .moviecovertb, and screenshots
        at the bottom.
        """
        tree = self.parse_html(html)
        movie = JAVMovie()
        movie.source_urls[self.SOURCE_NAME] = url

        # ── Page title / H1 ─────────────────────────────────────
        h1 = tree.css_first("h1, .entry-header h1")
        if h1:
            full_title = self.text(h1)
            # Title often starts with DVD-ID, e.g., "CJOD-523 - Full title here"
            m = re.match(r"^([A-Z]+-\d+)\s*[-–]\s*(.+)", full_title, re.IGNORECASE)
            if m:
                movie.dvd_id = self.normalize_id(m.group(1))
                movie.title = self.clean_text(m.group(2))
            else:
                movie.title = self.clean_text(full_title)

        # ── Cover image ──────────────────────────────────────────
        poster = tree.css_first("#poster-container img, .moviecovertb img")
        if poster:
            movie.cover_url = self.attr(poster, "src")

        # Thumbnail
        thumb = tree.css_first("#thumbnailContainer img")
        if thumb:
            movie.thumbnail_url = self.attr(thumb, "src")

        # ── Info paragraphs (<p><b>Label:</b> value</p>) ─────────
        info_container = tree.css_first(".col-md-10, .col-lg-10")
        if info_container:
            paragraphs = info_container.css("p")
            for p in paragraphs:
                bold = p.css_first("b")
                if not bold:
                    continue
                label = self.text(bold).lower().strip().rstrip(":")

                if "title" in label:
                    # Title value is text after bold, before any links
                    raw = p.text(strip=True)
                    # Remove the label prefix
                    val = re.sub(r"^title:\s*", "", raw, flags=re.IGNORECASE)
                    if val:
                        movie.title = self.clean_text(val)

                elif "dvd id" in label:
                    raw = p.text(strip=True)
                    val = re.sub(r"^dvd id:\s*", "", raw, flags=re.IGNORECASE)
                    movie.dvd_id = self.normalize_id(val)

                elif "content id" in label:
                    raw = p.text(strip=True)
                    val = re.sub(r"^content id:\s*", "", raw, flags=re.IGNORECASE)
                    movie.content_id = self.clean_text(val)

                elif "release date" in label:
                    raw = p.text(strip=True)
                    val = re.sub(r"^release date:\s*", "", raw, flags=re.IGNORECASE)
                    movie.release_date = self.clean_text(val)

                elif "runtime" in label:
                    raw = p.text(strip=True)
                    val = re.sub(r"^runtime:\s*", "", raw, flags=re.IGNORECASE)
                    movie.runtime = self.clean_text(val)

                elif "studio" in label:
                    link = p.css_first("a")
                    movie.studio = self.clean_text(self.text(link)) if link else None

                elif "director" in label:
                    raw = p.text(strip=True)
                    val = re.sub(r"^director:\s*", "", raw, flags=re.IGNORECASE)
                    movie.director = self.clean_text(val) if val.strip() else None

                elif "series" in label or "jav series" in label:
                    link = p.css_first("a")
                    movie.series = self.clean_text(self.text(link)) if link else None

                elif "genre" in label:
                    genre_links = p.css("a")
                    for gl in genre_links:
                        g = self.clean_text(self.text(gl))
                        if g and g not in movie.genres:
                            movie.genres.append(g)

                elif "idol" in label or "actress" in label:
                    actor_links = p.css("a")
                    for al in actor_links:
                        name = self.clean_text(self.text(al))
                        href = self.attr(al, "href")
                        if name:
                            movie.performers.append(Performer(
                                name=name,
                                profile_url=self.abs_url(href) if href else None,
                                source=self.SOURCE_NAME,
                            ))

        # ── Trailer video ────────────────────────────────────────
        video_source = tree.css_first("#jav-player source, video source")
        if video_source:
            movie.trailer_url = self.attr(video_source, "src")

        # ── Screenshots ──────────────────────────────────────────
        # JavDatabase shows sample images at the bottom
        sample_images = tree.css(".entry-content img[src*='pics.dmm'], img[src*='sample']")
        for img in sample_images:
            src = self.attr(img, "src")
            if src and src != movie.cover_url and src not in movie.screenshot_urls:
                movie.screenshot_urls.append(src)

        return movie if movie.dvd_id else None

    # ── Idol detail ──────────────────────────────────────────────

    async def get_performer(self, name: str) -> Optional[Performer]:
        """Scrape an idol profile page from JavDatabase."""
        slug = name.lower().replace(" ", "-")
        url = f"{self.BASE_URL}/idols/{slug}/"
        try:
            html = await self.fetch(url)
            return self._parse_idol(html, url)
        except Exception as e:
            logger.warning(f"JavDatabase idol scrape failed for {name}: {e}")
            return None

    def _parse_idol(self, html: str, url: str) -> Optional[Performer]:
        tree = self.parse_html(html)
        performer = Performer(name="", source=self.SOURCE_NAME)

        # Name from h1
        h1 = tree.css_first("h1.idol-name, h1")
        if h1:
            raw = self.text(h1)
            # Remove suffix like "- JAV Profile"
            name = re.sub(r"\s*-\s*JAV\s+Profile.*$", "", raw, flags=re.IGNORECASE)
            performer.name = self.clean_text(name) or ""

        # Image
        img = tree.css_first(".idol-portrait img")
        if img:
            performer.image_url = self.attr(img, "src")

        performer.profile_url = url

        # Parse the info block - uses <b>Label:</b> value pattern
        info_div = tree.css_first(".col-12.col-xxl-7, .col-xl-7")
        if info_div:
            raw_text = info_div.text()

            # Age
            m = re.search(r"Age:\s*(\d+)", raw_text)
            if m:
                performer.age = int(m.group(1))

            # DOB
            m = re.search(r"DOB:\s*([\d-]+)", raw_text)
            if m:
                performer.dob = m.group(1)

            # Height
            m = re.search(r"Height:\s*(\d+\s*cm)", raw_text)
            if m:
                performer.height = m.group(1)

            # Measurements
            m = re.search(r"Measurements:\s*([\d-]+)", raw_text)
            if m:
                performer.measurements = m.group(1)

            # Cup
            m = re.search(r"Cup:\s*([A-Z]+)", raw_text, re.IGNORECASE)
            if m:
                performer.cup_size = m.group(1).upper()

            # Birthplace
            m = re.search(r"Birthplace:\s*(\w+)", raw_text)
            if m:
                performer.birthplace = m.group(1)

            # JP name
            m = re.search(r"JP:\s*(.+?)(?:\s|$)", raw_text)
            if m:
                performer.name_jp = self.clean_text(m.group(1))

            # Twitter link
            twitter = info_div.css_first("a[href*='twitter.com']")
            if twitter:
                performer.twitter = self.attr(twitter, "href")

            # Debut
            m = re.search(r"Debut:\s*([\d-]+)", raw_text)
            if m:
                performer.debut_date = m.group(1)

            # Hair
            m = re.search(r"Hair Length\(s\):\s*(\w+)", raw_text)
            if m:
                performer.hair_length = m.group(1)
            m = re.search(r"Hair Color\(s\):\s*(\w+)", raw_text)
            if m:
                performer.hair_color = m.group(1)

            # Tags
            tag_links = info_div.css("a.idol-box-link")
            for tl in tag_links:
                tag = self.clean_text(self.text(tl))
                if tag and tag not in performer.tags and not tag.replace("-", "").isdigit():
                    performer.tags.append(tag)

        return performer if performer.name else None
