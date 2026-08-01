"""Tests for the official MCP Registry search backend."""

import json
from pathlib import Path

import pytest

import magg
from magg.discovery.search import ToolSearchEngine

SAMPLE_RESPONSE = {
    "servers": [
        {
            "server": {
                "name": "io.github.example/files",
                "description": "Filesystem access",
                "version": "1.2.0",
                "repository": {"url": "https://github.com/example/files", "source": "github"},
                "packages": [
                    {
                        "registryType": "npm",
                        "identifier": "example-files-mcp",
                        "version": "1.2.0",
                        "transport": {"type": "stdio"},
                    }
                ],
            },
            "_meta": {
                "io.modelcontextprotocol.registry/official": {
                    "status": "active",
                    "updatedAt": "2026-01-01T00:00:00Z",
                }
            },
        },
        {
            "server": {
                "name": "com.example/hosted",
                "description": "Hosted server",
                "version": "0.1.0",
                "websiteUrl": "https://example.com",
                "remotes": [{"type": "streamable-http", "url": "https://mcp.example.com/mcp"}],
            },
            "_meta": {},
        },
        {
            "server": {
                "name": "io.github.example/py-tool",
                "description": "Python tool",
                "version": "2.0.0",
                "packages": [
                    {
                        "registryType": "pypi",
                        "identifier": "py-tool-mcp",
                        "version": "2.0.0",
                        "transport": {"type": "stdio"},
                    }
                ],
            },
            "_meta": {},
        },
        {"server": {}, "_meta": {}},
    ],
    "metadata": {"count": 4},
}


class TestRegistryResultParsing:
    """Test parsing of official MCP Registry responses."""

    def test_parse_results(self):
        results = ToolSearchEngine._parse_registry_results(SAMPLE_RESPONSE)

        # Entry without a name is dropped
        assert len(results) == 3
        assert all(r.source == "mcp-registry" for r in results)

        npm = results[0]
        assert npm.name == "io.github.example/files"
        assert npm.url == "https://github.com/example/files"
        assert npm.install_command == "npx -y example-files-mcp"
        assert "npm" in npm.tags
        assert npm.metadata["version"] == "1.2.0"
        assert npm.metadata["status"] == "active"

        hosted = results[1]
        assert hosted.url == "https://example.com"
        assert hosted.install_command is None
        assert "remote" in hosted.tags
        assert hosted.metadata["remotes"][0]["url"] == "https://mcp.example.com/mcp"

        pypi = results[2]
        assert pypi.install_command == "uvx py-tool-mcp"

    def test_parse_empty_response(self):
        assert ToolSearchEngine._parse_registry_results({}) == []
        assert ToolSearchEngine._parse_registry_results({"servers": []}) == []

    def test_install_command_types(self):
        cmd = ToolSearchEngine._registry_install_command
        assert cmd([{"registryType": "npm", "identifier": "a"}]) == "npx -y a"
        assert cmd([{"registryType": "pypi", "identifier": "b"}]) == "uvx b"
        assert cmd([{"registryType": "oci", "identifier": "ghcr.io/x/y:1"}]) == "docker run --rm -i ghcr.io/x/y:1"
        # Unknown registry types are skipped; later known types still win
        assert cmd([{"registryType": "nuget", "identifier": "c"}, {"registryType": "npm", "identifier": "d"}]) == (
            "npx -y d"
        )
        assert cmd([]) is None
        assert cmd([{"registryType": "npm"}]) is None


class TestServerManifest:
    """Test Magg's own server.json registry manifest."""

    def test_server_json_consistency(self):
        root = Path(__file__).parent.parent.parent
        manifest = json.loads((root / "server.json").read_text())

        assert manifest["name"] == "io.github.sitbon/magg"
        assert manifest["repository"]["url"] == "https://github.com/sitbon/magg"

        package = manifest["packages"][0]
        assert package["registryType"] == "pypi"
        assert package["identifier"] == "magg"
        # Top-level and package versions must stay in sync for publishing
        assert package["version"] == manifest["version"]
        assert package["transport"]["type"] == "stdio"

    def test_server_json_version_matches_package(self):
        """Fail release PRs that bump pyproject.toml but forget server.json."""
        if magg.__version__ == "unknown":
            pytest.skip("magg package metadata not available")

        root = Path(__file__).parent.parent.parent
        manifest = json.loads((root / "server.json").read_text())
        assert manifest["version"] == magg.__version__
