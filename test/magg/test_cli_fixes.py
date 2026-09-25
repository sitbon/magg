"""Tests for auth CLI and server search robustness fixes."""

import asyncio
import json
import os
import subprocess
import time

import pytest

from magg.auth import BearerAuthManager
from magg.cli import cmd_auth, create_parser
from magg.discovery.search import ToolSearchEngine
from magg.settings import BearerAuthConfig


class TestAuthCLI:
    """magg auth commands."""

    @pytest.fixture
    def auth_env(self, tmp_path, monkeypatch):
        """Point HOME and the config at a temp dir with no ~/.ssh."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("MAGG_PRIVATE_KEY", raising=False)
        return tmp_path / "config" / "config.json"

    async def run_auth(self, config_path, *argv):
        args = create_parser().parse_args(["--config", str(config_path), "auth", *argv])
        return await cmd_auth(args)

    def test_generate_keypair_creates_missing_parents(self, tmp_path):
        key_path = tmp_path / "home" / ".ssh" / "magg"
        manager = BearerAuthManager(BearerAuthConfig(key_path=key_path))

        manager.generate_keys()

        private_path = key_path / "magg.key"
        assert private_path.exists()
        assert oct(private_path.stat().st_mode)[-3:] == "600"

    @pytest.mark.asyncio
    async def test_init_twice_reports_error(self, auth_env, tmp_path, capsys):
        key_path = tmp_path / "keys"

        assert await self.run_auth(auth_env, "init", "--key-path", str(key_path)) == 0
        assert await self.run_auth(auth_env, "init", "--key-path", str(key_path)) == 1

        assert "already exists" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_init_saves_custom_key_path(self, auth_env, tmp_path):
        key_path = tmp_path / "keys"

        assert await self.run_auth(auth_env, "init", "--key-path", str(key_path)) == 0

        saved = json.loads((auth_env.parent / "auth.json").read_text())
        assert saved["bearer"]["key_path"] == str(key_path)

    @pytest.mark.asyncio
    async def test_private_key_export_is_shell_safe(self, auth_env, tmp_path, capsys):
        key_path = tmp_path / "keys"
        assert await self.run_auth(auth_env, "init", "--key-path", str(key_path)) == 0
        capsys.readouterr()

        assert await self.run_auth(auth_env, "private-key", "--export") == 0
        line = capsys.readouterr().out.strip()

        result = subprocess.run(
            ["sh", "-c", f'{line}; printf %s "$MAGG_PRIVATE_KEY"'], capture_output=True, text=True, check=True
        )
        pem = result.stdout.replace("\\n", "\n")
        assert pem == (key_path / "magg.key").read_text()


class TestSearch:
    """ToolSearchEngine handles missing fields and slow sources."""

    def test_github_null_description(self):
        data = {
            "items": [
                {"name": "no-desc", "description": None, "html_url": "https://github.com/a/b"},
                {"name": "mcp-thing", "description": "An MCP server", "html_url": "https://github.com/a/c"},
            ]
        }

        results = ToolSearchEngine._parse_github_results(data)

        assert [r.name for r in results] == ["mcp-thing"]

    def test_npm_null_author_and_description(self):
        data = {"objects": [{"package": {"name": "pkg", "description": None, "author": None}}]}

        results = ToolSearchEngine._parse_npm_results(data)

        assert results[0].description == ""
        assert results[0].metadata["author"] is None

    @pytest.mark.asyncio
    async def test_search_all_runs_sources_concurrently(self, monkeypatch):
        async def slow(self, query, limit):
            await asyncio.sleep(0.3)
            return []

        async def broken(self, query, limit):
            raise RuntimeError("offline")

        monkeypatch.setattr(ToolSearchEngine, "search_registry", slow)
        monkeypatch.setattr(ToolSearchEngine, "search_glama", slow)
        monkeypatch.setattr(ToolSearchEngine, "search_github", slow)
        monkeypatch.setattr(ToolSearchEngine, "search_npm", broken)

        engine = ToolSearchEngine()
        start = time.monotonic()
        results = await engine.search_all("x")
        elapsed = time.monotonic() - start

        assert elapsed < 0.8
        assert results == {"mcp-registry": [], "glama": [], "github": [], "npm": []}


@pytest.fixture(autouse=True)
def _no_real_private_key(monkeypatch):
    # A MAGG_PRIVATE_KEY in the developer's environment would change auth behavior
    if "MAGG_PRIVATE_KEY" in os.environ:
        monkeypatch.delenv("MAGG_PRIVATE_KEY")
