"""Tool search and discovery capabilities for Magg.

TODO: Add support for mcpservers.org.
"""

import asyncio
import aiohttp
import json
from dataclasses import dataclass
from urllib.parse import urlencode
import logging
from typing import Any


@dataclass
class ToolSearchResult:
    """Result from a tool search."""
    name: str
    description: str
    source: str
    url: str | None = None
    tags: list[str] = None
    rating: float | None = None
    install_command: str | None = None
    metadata: dict[str, Any] | None = None


class ToolSearchEngine:
    """Engine for searching and discovering MCP tools."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def search_glama(self, query: str, limit: int = 10) -> list[ToolSearchResult]:
        """Search glama.ai for MCP tools using their API."""
        if not self.session:
            raise RuntimeError("ToolSearchEngine must be used as async context manager")

        try:
            # Use the actual Glama MCP API
            url = "https://glama.ai/api/mcp/v1/servers"
            params = {
                "query": query,
                "first": limit
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_glama_results(data)
                else:
                    self.logger.warning(f"Glama search failed with status {response.status}")
                    return []

        except Exception as e:
            self.logger.error(f"Error searching glama.ai: {e}")
            return []

    def _parse_glama_results(self, data: dict[str, Any]) -> list[ToolSearchResult]:
        """Parse glama.ai search results."""
        results = []

        for server in data.get("servers", []):
            # Extract hosting type from attributes for intelligent configuration
            hosting_type = self._get_hosting_type(server.get("attributes", []))

            # Generate install command based on repository and hosting type
            install_command = self._generate_install_command(server, hosting_type)

            # Convert glama result to our format
            result = ToolSearchResult(
                name=server.get("name", ""),
                description=server.get("description", ""),
                source="glama",
                url=server.get("url", ""),
                tags=self._extract_tags(server),
                rating=None,  # Glama doesn't provide ratings in this format
                install_command=install_command,
                metadata={
                    **server,
                    "hosting_type": hosting_type,
                    "namespace": server.get("namespace"),
                    "slug": server.get("slug"),
                    "tools": server.get("tools", []),
                    "environment_variables": server.get("environmentVariablesJsonSchema"),
                    "license": server.get("spdxLicense", {}).get("name") if server.get("spdxLicense") else None
                }
            )
            results.append(result)

        return results

    def _get_hosting_type(self, attributes: list[str]) -> str:
        """Determine hosting type from Glama server attributes."""
        if "hosting:remote-capable" in attributes:
            return "remote"
        elif "hosting:local-only" in attributes:
            return "local"
        elif "hosting:hybrid" in attributes:
            return "hybrid"
        else:
            return "local"  # Default to local

    def _generate_install_command(self, server: dict[str, Any], hosting_type: str) -> str:
        """Generate appropriate install command based on server metadata."""
        repository = server.get("repository", {})
        repo_url = repository.get("url", "") if repository else ""

        if repo_url:
            if "github.com" in repo_url:
                return f"git clone {repo_url}"
            elif "npm" in repo_url or "npmjs" in repo_url:
                # Try to extract package name from NPM URL
                package_name = server.get("slug", server.get("name", ""))
                return f"npm install {package_name}"

        # Fallback based on namespace/slug
        namespace = server.get("namespace", "")
        slug = server.get("slug", "")
        if namespace and slug:
            return f"# Install {namespace}/{slug} - check {server.get('url', 'repository')} for instructions"

        return f"# Manual installation required - see {server.get('url', 'documentation')}"

    def _extract_tags(self, server: dict[str, Any]) -> list[str]:
        """Extract meaningful tags from server metadata."""
        tags = []

        # Add hosting type as tag
        attributes = server.get("attributes", [])
        if "hosting:remote-capable" in attributes:
            tags.append("remote")
        if "hosting:local-only" in attributes:
            tags.append("local")
        if "hosting:hybrid" in attributes:
            tags.append("hybrid")
        if "author:official" in attributes:
            tags.append("official")

        # Add license as tag if available
        license_info = server.get("spdxLicense", {})
        if license_info and license_info.get("name"):
            tags.append(license_info["name"].lower())

        # Add namespace as tag
        namespace = server.get("namespace")
        if namespace:
            tags.append(f"by:{namespace}")

        return tags

    async def search_github(self, query: str, limit: int = 10) -> list[ToolSearchResult]:
        """Search GitHub for MCP tools and servers."""
        if not self.session:
            raise RuntimeError("ToolSearchEngine must be used as async context manager")

        try:
            # Search GitHub for MCP-related repositories
            search_query = f"{query} mcp model-context-protocol"
            url = "https://api.github.com/search/repositories"
            params = {
                "q": search_query,
                "sort": "stars",
                "order": "desc",
                "per_page": limit
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_github_results(data)
                else:
                    self.logger.warning(f"GitHub search failed with status {response.status}")
                    return []

        except Exception as e:
            self.logger.error(f"Error searching GitHub: {e}")
            return []

    def _parse_github_results(self, data: dict[str, Any]) -> list[ToolSearchResult]:
        """Parse GitHub search results."""
        results = []

        for item in data.get("items", []):
            # Try to determine if this is an MCP server
            is_mcp_server = any(keyword in item.get("description", "").lower()
                              for keyword in ["mcp", "model context protocol", "mcp server"])

            if is_mcp_server:
                result = ToolSearchResult(
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    source="github",
                    url=item.get("html_url"),
                    tags=item.get("topics", []),
                    rating=item.get("stargazers_count", 0) / 100.0,  # Normalize stars to rating
                    install_command=f"git clone {item.get('clone_url')}",
                    metadata={
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "language": item.get("language"),
                        "updated_at": item.get("updated_at")
                    }
                )
                results.append(result)

        return results

    async def search_npm(self, query: str, limit: int = 10) -> list[ToolSearchResult]:
        """Search NPM for MCP-related packages."""
        if not self.session:
            raise RuntimeError("ToolSearchEngine must be used as async context manager")

        try:
            # Search NPM registry
            url = "https://registry.npmjs.org/-/v1/search"
            params = {
                "text": f"{query} mcp",
                "size": limit
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_npm_results(data)
                else:
                    self.logger.warning(f"NPM search failed with status {response.status}")
                    return []

        except Exception as e:
            self.logger.error(f"Error searching NPM: {e}")
            return []

    def _parse_npm_results(self, data: dict[str, Any]) -> list[ToolSearchResult]:
        """Parse NPM search results."""
        results = []

        for item in data.get("objects", []):
            package = item.get("package", {})

            result = ToolSearchResult(
                name=package.get("name", ""),
                description=package.get("description", ""),
                source="npm",
                url=f"https://www.npmjs.com/package/{package.get('name')}",
                tags=package.get("keywords", []),
                install_command=f"npm install {package.get('name')}",
                metadata={
                    "version": package.get("version"),
                    "author": package.get("author", {}).get("name"),
                    "license": package.get("license")
                }
            )
            results.append(result)

        return results

    async def search_all(self, query: str, limit_per_source: int = 5) -> dict[str, list[ToolSearchResult]]:
        """Search all available sources for tools."""
        tasks = [
            ("glama", self.search_glama(query, limit_per_source)),
            ("github", self.search_github(query, limit_per_source)),
            ("npm", self.search_npm(query, limit_per_source))
        ]

        results = {}
        for source, task in tasks:
            try:
                results[source] = await task
            except Exception as e:
                self.logger.error(f"Error searching {source}: {e}")
                results[source] = []

        return results

    def rank_results(self, results: list[ToolSearchResult]) -> list[ToolSearchResult]:
        """Rank search results by relevance and quality."""
        def calculate_score(result: ToolSearchResult) -> float:
            score = 0.0

            # Base score from rating
            if result.rating:
                score += result.rating * 10

            # Bonus for certain sources
            source_bonus = {
                "glama.ai": 5.0,
                "github": 3.0,
                "npm": 2.0
            }
            score += source_bonus.get(result.source, 0.0)

            # Bonus for having install command
            if result.install_command:
                score += 2.0

            # Bonus for having tags
            if result.tags:
                score += len(result.tags) * 0.5

            return score

        # Sort by calculated score in descending order
        return sorted(results, key=calculate_score, reverse=True)


class ToolCatalog:
    """Catalog of discovered tools with caching and metadata."""

    def __init__(self):
        self.catalog: dict[str, ToolSearchResult] = {}
        self.search_history: list[tuple[str, float]] = []  # (query, timestamp)
        self.logger = logging.getLogger(__name__)

    def add_result(self, result: ToolSearchResult) -> None:
        """Add a search result to the catalog."""
        key = f"{result.source}:{result.name}"
        self.catalog[key] = result

    def add_results(self, results: list[ToolSearchResult]) -> None:
        """Add multiple search results to the catalog."""
        for result in results:
            self.add_result(result)

    def get_by_name(self, name: str) -> list[ToolSearchResult]:
        """Get all results matching a name."""
        return [result for result in self.catalog.values()
                if name.lower() in result.name.lower()]

    def get_by_source(self, source: str) -> list[ToolSearchResult]:
        """Get all results from a specific source."""
        return [result for result in self.catalog.values()
                if result.source == source]

    def get_by_tags(self, tags: list[str]) -> list[ToolSearchResult]:
        """Get all results matching any of the given tags."""
        matching = []
        for result in self.catalog.values():
            if result.tags and any(tag in result.tags for tag in tags):
                matching.append(result)
        return matching

    def get_top_rated(self, limit: int = 10) -> list[ToolSearchResult]:
        """Get top-rated tools from the catalog."""
        rated_tools = [result for result in self.catalog.values() if result.rating]
        return sorted(rated_tools, key=lambda x: x.rating, reverse=True)[:limit]

    def search_catalog(self, query: str) -> list[ToolSearchResult]:
        """Search the local catalog for tools."""
        query_lower = query.lower()
        matching = []

        for result in self.catalog.values():
            # Search in name and description
            if (query_lower in result.name.lower() or
                query_lower in result.description.lower()):
                matching.append(result)
                continue

            # Search in tags
            if result.tags and any(query_lower in tag.lower() for tag in result.tags):
                matching.append(result)

        return matching

    def export_catalog(self) -> dict[str, Any]:
        """Export catalog to a serializable format."""
        return {
            "catalog": {
                key: {
                    "name": result.name,
                    "description": result.description,
                    "source": result.source,
                    "url": result.url,
                    "tags": result.tags,
                    "rating": result.rating,
                    "install_command": result.install_command,
                    "metadata": result.metadata
                }
                for key, result in self.catalog.items()
            },
            "search_history": self.search_history
        }

    def import_catalog(self, data: dict[str, Any]) -> None:
        """Import catalog from serialized format."""
        self.catalog.clear()

        for key, item_data in data.get("catalog", {}).items():
            result = ToolSearchResult(
                name=item_data["name"],
                description=item_data["description"],
                source=item_data["source"],
                url=item_data.get("url"),
                tags=item_data.get("tags"),
                rating=item_data.get("rating"),
                install_command=item_data.get("install_command"),
                metadata=item_data.get("metadata")
            )
            self.catalog[key] = result

        self.search_history = data.get("search_history", [])
