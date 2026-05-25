"""Data merger - combines results from multiple scrapers into a unified JAVMovie."""

from __future__ import annotations

import logging
from typing import Optional

from .models import JAVMovie, Performer

logger = logging.getLogger(__name__)


def merge_movies(movies: list[JAVMovie]) -> JAVMovie:
    """Merge multiple JAVMovie objects from different sources into one.

    Priority order for scalar fields: first non-None value wins.
    List fields are merged with deduplication.
    Performers are merged by name similarity.
    """
    if not movies:
        return JAVMovie()
    if len(movies) == 1:
        return movies[0]

    merged = JAVMovie()

    # Merge scalar fields - first non-empty wins
    scalar_fields = [
        "dvd_id", "content_id", "title", "title_jp", "release_date",
        "runtime", "director", "studio", "maker", "label", "series",
        "cover_url", "thumbnail_url", "trailer_url", "rating",
    ]

    for field in scalar_fields:
        for movie in movies:
            val = getattr(movie, field, None)
            if val is not None and val != "":
                setattr(merged, field, val)
                break

    # Merge rating - prefer highest count, or average if counts similar
    ratings = [(m.rating, m.rating_count) for m in movies if m.rating is not None]
    if ratings:
        # Use the one with most votes, or first available
        best = max(ratings, key=lambda x: x[1] or 0)
        merged.rating = best[0]
        merged.rating_count = best[1]

    # Merge list fields with deduplication
    _merge_list(merged, movies, "genres")
    _merge_list(merged, movies, "tags")
    _merge_list(merged, movies, "screenshot_urls")

    # Merge performers by name
    merged.performers = _merge_performers([p for m in movies for p in m.performers])

    # Merge source URLs
    for movie in movies:
        merged.source_urls.update(movie.source_urls)

    return merged


def _merge_list(merged: JAVMovie, movies: list[JAVMovie], field: str):
    """Merge a list field across movies, deduplicating by lowercase comparison."""
    seen: set[str] = set()
    result: list[str] = []
    for movie in movies:
        for item in getattr(movie, field, []):
            key = item.lower().strip()
            if key not in seen:
                seen.add(key)
                result.append(item)
    setattr(merged, field, result)


def _merge_performers(performers: list[Performer]) -> list[Performer]:
    """Merge performers by name, combining data from multiple sources."""
    by_name: dict[str, Performer] = {}

    for p in performers:
        key = p.name.lower().strip()
        if key not in by_name:
            by_name[key] = p.model_copy()
        else:
            existing = by_name[key]
            # Fill in missing fields from this source
            for field in [
                "name_jp", "image_url", "profile_url", "age", "dob",
                "height", "measurements", "cup_size", "birthplace",
                "twitter", "debut_date", "hair_color", "hair_length",
            ]:
                if getattr(existing, field, None) is None:
                    val = getattr(p, field, None)
                    if val is not None:
                        setattr(existing, field, val)
            # Merge tags
            existing_tags = set(t.lower() for t in existing.tags)
            for tag in p.tags:
                if tag.lower() not in existing_tags:
                    existing.tags.append(tag)
                    existing_tags.add(tag.lower())

    return list(by_name.values())
