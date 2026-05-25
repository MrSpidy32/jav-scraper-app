"""
JAV Ultimate Scraper - Multi-source JAV metadata aggregator.

Scrapes and merges data from:
  - javdb.com
  - javlibrary.com
  - javdatabase.com

Usage:
    from javdb.api import JAVScraper

    scraper = JAVScraper()
    result = scraper.search("SSIS-001")
    print(result.model_dump_json(indent=2))
"""

__version__ = "1.0.0"
