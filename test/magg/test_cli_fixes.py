"""Tests for auth CLI and server search robustness fixes."""

import asyncio
import json
import os
import subprocess
import sys

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
    async def test_custom_key_path_is_used_afterwards(self, auth_env, tmp_path, capsys):
        # Previously the key was generated at --key-path, but later commands looked in the default place
        key_path = tmp_path / "keys"

        assert await self.run_auth(auth_env, "init", "--key-path", str(key_path)) == 0
        capsys.readouterr()

        assert await self.run_auth(auth_env, "token", "-q") == 0
        token = capsys.readouterr().out.strip()
        assert token.count(".") == 2

        manager = BearerAuthManager(BearerAuthConfig(key_path=key_path))
        manager.load_keys()
        assert manager.provider is not None
        assert json.loads((auth_env.parent / "auth.json").read_text())["bearer"]["key_path"] == str(key_path)

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
        # Each source waits until all three have started, which can only happen if they run together
        all_started = asyncio.Barrier(3)

        def source(name):
            async def search(self, query, limit):
                await all_started.wait()
                return [name]

            return search

        async def broken(self, query, limit):
            raise RuntimeError("offline")

        monkeypatch.setattr(ToolSearchEngine, "search_registry", source("registry"))
        monkeypatch.setattr(ToolSearchEngine, "search_glama", source("glama"))
        monkeypatch.setattr(ToolSearchEngine, "search_github", source("github"))
        monkeypatch.setattr(ToolSearchEngine, "search_npm", broken)

        results = await asyncio.wait_for(ToolSearchEngine().search_all("x"), 5)

        # One failing source doesn't affect the others
        assert results == {"mcp-registry": ["registry"], "glama": ["glama"], "github": ["github"], "npm": []}


class TestInvalidSettings:
    """Bad MAGG_* values produce a readable error, not a traceback."""

    def test_invalid_env_value(self, tmp_path):
        env = {**os.environ, "MAGG_AUTO_RELOAD": "maybe", "MAGG_CONFIG_PATH": str(tmp_path / "config.json")}

        result = subprocess.run(
            [sys.executable, "-m", "magg", "server", "list"], capture_output=True, text=True, env=env, timeout=60
        )

        assert result.returncode == 1
        assert "MAGG_AUTO_RELOAD" in result.stderr
        assert "Traceback" not in result.stderr
