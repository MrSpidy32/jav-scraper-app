"""Unified data models for JAV metadata."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class Performer(BaseModel):
    """A performer / actress / idol."""

    name: str
    name_jp: Optional[str] = None
    image_url: Optional[str] = None
    profile_url: Optional[str] = None
    age: Optional[int] = None
    dob: Optional[str] = None
    height: Optional[str] = None
    measurements: Optional[str] = None
    cup_size: Optional[str] = None
    birthplace: Optional[str] = None
    twitter: Optional[str] = None
    debut_date: Optional[str] = None
    hair_color: Optional[str] = None
    hair_length: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    source: Optional[str] = None


class JAVMovie(BaseModel):
    """Unified JAV movie metadata from all sources."""

    # Core identifiers
    dvd_id: str = ""
    content_id: Optional[str] = None

    # Basic info
    title: Optional[str] = None
    title_jp: Optional[str] = None
    release_date: Optional[str] = None
    runtime: Optional[str] = None
    director: Optional[str] = None

    # Studio / maker / label
    studio: Optional[str] = None
    maker: Optional[str] = None
    label: Optional[str] = None
    series: Optional[str] = None

    # Media
    cover_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    trailer_url: Optional[str] = None
    screenshot_urls: list[str] = Field(default_factory=list)

    # Classification
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # Performers
    performers: list[Performer] = Field(default_factory=list)

    # Ratings / scores
    rating: Optional[float] = None
    rating_count: Optional[int] = None

    # Source URLs for reference
    source_urls: dict[str, str] = Field(default_factory=dict)

    # Raw per-source data before merge
    _sources: dict[str, dict] = {}


class SearchResult(BaseModel):
    """A single search result entry."""

    dvd_id: str
    title: Optional[str] = None
    cover_url: Optional[str] = None
    release_date: Optional[str] = None
    performers: list[str] = Field(default_factory=list)
    detail_url: str = ""
    source: str = ""


class ScrapeResult(BaseModel):
    """Wrapper for a scrape operation result."""

    success: bool = True
    movie: Optional[JAVMovie] = None
    errors: list[str] = Field(default_factory=list)
    sources_scraped: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)
