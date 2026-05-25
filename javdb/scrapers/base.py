"""Base scraper with shared HTTP client, retry logic, and parsing utilities."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urljoin, quote

import httpx
from curl_cffi import requests as curl_requests
from curl_cffi.requests.errors import RequestsError
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..models import JAVMovie, Performer, SearchResult
import random

logger = logging.getLogger(__name__)

# Shared user-agent rotator
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

class BaseScraper:
    """Base class for all JAV site scrapers."""

    SOURCE_NAME: str = "base"
    BASE_URL: str = ""

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        proxy: Optional[str] = None,
        cookies: Optional[dict] = None,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.proxy = proxy
        self.cookies = cookies or {}
        self._client: Optional[curl_requests.AsyncSession] = None

    # ── HTTP client ──────────────────────────────────────────────

    def _build_headers(self) -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    async def _get_client(self) -> curl_requests.AsyncSession:
        if self._client is None or getattr(self._client, "closed", True):
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
            self._client = curl_requests.AsyncSession(
                timeout=self.timeout,
                impersonate="chrome",
                proxies=proxies,
                cookies=self.cookies,
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(RequestsError),
    )
    async def fetch(self, url: str, headers: Optional[dict] = None) -> str:
        """Fetch a URL and return the response text."""
        client = await self._get_client()
        hdrs = self._build_headers()
        if headers:
            hdrs.update(headers)
        resp = await client.get(url, headers=hdrs)
        resp.raise_for_status()
        return resp.text

    async def fetch_bytes(self, url: str) -> bytes:
        """Fetch raw bytes (for images, etc.)."""
        client = await self._get_client()
        resp = await client.get(url, headers=self._build_headers())
        resp.raise_for_status()
        return resp.content

    async def close(self):
        if self._client:
            await self._client.close()

    # ── Parsing helpers ──────────────────────────────────────────

    @staticmethod
    def parse_html(html: str) -> HTMLParser:
        return HTMLParser(html)

    @staticmethod
    def text(node, default: str = "") -> str:
        """Extract cleaned text from a selectolax node."""
        if node is None:
            return default
        t = node.text(strip=True)
        return t if t else default

    @staticmethod
    def attr(node, name: str, default: str = "") -> str:
        if node is None:
            return default
        val = node.attributes.get(name)
        return val if val else default

    def abs_url(self, relative: str) -> str:
        if relative.startswith("http"):
            return relative
        return urljoin(self.BASE_URL, relative)

    @staticmethod
    def normalize_id(dvd_id: str) -> str:
        """Normalize a JAV ID to standard format: ABC-123."""
        dvd_id = dvd_id.strip().upper()
        # Handle formats like abc00123 -> ABC-123
        m = re.match(r"^([A-Z]+)-?0*(\d+)$", dvd_id)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        return dvd_id

    @staticmethod
    def clean_text(s: Optional[str]) -> Optional[str]:
        if not s:
            return None
        s = re.sub(r"\s+", " ", s).strip()
        return s if s else None

    # ── Abstract interface ───────────────────────────────────────

    async def search(self, query: str) -> list[SearchResult]:
        raise NotImplementedError

    async def get_movie(self, dvd_id: str) -> Optional[JAVMovie]:
        raise NotImplementedError

    async def get_movie_by_url(self, url: str) -> Optional[JAVMovie]:
        raise NotImplementedError

    # ── Context manager ──────────────────────────────────────────

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
