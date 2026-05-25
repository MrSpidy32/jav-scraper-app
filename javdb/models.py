"""Unified data models for JAV metadata."""

from __future__ import annotations

from datetime import date
from typing import Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    import json
    import copy

    class FieldInfo:
        def __init__(self, default=None, default_factory=None):
            self.default = default
            self.default_factory = default_factory

    def Field(default=None, default_factory=None, **kwargs):
        return FieldInfo(default=default, default_factory=default_factory)

    class BaseModel:
        def __init__(self, **kwargs):
            cls = self.__class__
            annotations = getattr(cls, '__annotations__', {})
            
            defaults = {}
            for name in annotations:
                if hasattr(cls, name):
                    defaults[name] = getattr(cls, name)
                else:
                    defaults[name] = None
            
            for name in annotations:
                if name in kwargs:
                    setattr(self, name, kwargs[name])
                else:
                    default_val = defaults.get(name)
                    if isinstance(default_val, FieldInfo):
                        if default_val.default_factory is not None:
                            setattr(self, name, default_val.default_factory())
                        else:
                            setattr(self, name, default_val.default)
                    elif default_val is not None:
                        if isinstance(default_val, list):
                            setattr(self, name, list(default_val))
                        elif isinstance(default_val, dict):
                            setattr(self, name, dict(default_val))
                        else:
                            setattr(self, name, default_val)
                    else:
                        setattr(self, name, None)

            # Set any extra arguments that aren't in annotations
            for k, v in kwargs.items():
                if k not in annotations:
                    setattr(self, k, v)

        def model_copy(self, deep=False):
            if deep:
                return copy.deepcopy(self)
            else:
                return copy.copy(self)

        def model_dump(self):
            def dump_val(v):
                if isinstance(v, BaseModel):
                    return v.model_dump()
                elif isinstance(v, list):
                    return [dump_val(x) for x in v]
                elif isinstance(v, dict):
                    return {k: dump_val(val) for k, val in v.items()}
                else:
                    return v
            
            annotations = getattr(self.__class__, '__annotations__', {})
            res = {}
            for name in annotations:
                if name.startswith('_'):
                    continue
                if hasattr(self, name):
                    res[name] = dump_val(getattr(self, name))
            return res

        def model_dump_json(self, indent=None):
            return json.dumps(self.model_dump(), indent=indent, default=str)


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
