"""Simplified tool catalog for search functionality only."""

import json
import logging
from pathlib import Path
from typing import Any

from .search import ToolSearchEngine, ToolSearchResult, ToolCatalog


class CatalogManager:
    """Manages tool search catalog - search functionality only."""

    def __init__(self, catalog_path: Path | None = None):
        self.catalog_path = catalog_path or Path.cwd() / ".magg" / "search_cache.json"
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)

        self.search_catalog = ToolCatalog()
        self.logger = logging.getLogger(__name__)

        # Load existing search cache
        self.load_search_cache()

    def load_search_cache(self) -> None:
        """Load search cache from disk."""
        if not self.catalog_path.exists():
            return

        try:
            with open(self.catalog_path, 'r') as f:
                data = json.load(f)

            # Load search catalog cache
            if "search_catalog" in data:
                self.search_catalog.import_catalog(data["search_catalog"])

        except Exception as e:
            self.logger.error(f"Error loading search cache: {e}")

    def save_search_cache(self) -> None:
        """Save search cache to disk."""
        try:
            data = {
                "search_catalog": self.search_catalog.export_catalog()
            }

            with open(self.catalog_path, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            self.logger.error(f"Error saving search cache: {e}")

    async def search_only(self, query: str, limit_per_source: int = 5) -> dict[str, list[ToolSearchResult]]:
        """Search for tools without auto-adding to cache."""
        async with ToolSearchEngine() as search_engine:
            results = await search_engine.search_all(query, limit_per_source)
            return results

    async def search_and_cache(self, query: str, limit_per_source: int = 5) -> dict[str, list[ToolSearchResult]]:
        """Search for tools and update the cache."""
        async with ToolSearchEngine() as search_engine:
            results = await search_engine.search_all(query, limit_per_source)

            # Add all results to cache
            for source_results in results.values():
                self.search_catalog.add_results(source_results)

            # Save updated cache
            self.save_search_cache()

            return results

    def search_local_cache(self, query: str) -> list[ToolSearchResult]:
        """Search the local cache."""
        return self.search_catalog.search_catalog(query)

    def get_search_stats(self) -> dict[str, Any]:
        """Get statistics about the search cache."""
        total_cached = len(self.search_catalog.catalog)

        # Count by source
        source_counts = {}
        for result in self.search_catalog.catalog.values():
            source_counts[result.source] = source_counts.get(result.source, 0) + 1

        return {
            "total_cached": total_cached,
            "source_breakdown": source_counts,
            "cache_path": str(self.catalog_path)
        }
