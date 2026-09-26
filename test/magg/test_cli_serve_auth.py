"""Tests for serve command authentication behavior (GHSA-4jj7-7g54-cqrv)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from magg.cli import cmd_serve, create_parser
from magg.settings import ConfigManager


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Isolated environment for CLI serve auth tests."""
    monkeypatch.setenv("HOME", str(tmp_path))
    magg_dir = tmp_path / ".magg"
    magg_dir.mkdir(parents=True, exist_ok=True)
    config_file = magg_dir / "config.json"
    ssh_dir = tmp_path / ".ssh" / "magg"
    monkeypatch.setenv("MAGG_PATH", str(magg_dir))
    monkeypatch.delenv("MAGG_CONFIG_PATH", raising=False)
    monkeypatch.delenv("MAGG_READ_ONLY", raising=False)
    return {
        "config_file": config_file,
        "magg_dir": magg_dir,
        "ssh_dir": ssh_dir,
    }


def parse_args(*argv):
    """Parse CLI arguments."""
    return create_parser().parse_args(list(argv))


class TestServeAuthCLI:
    """Test CLI serve authentication defaults and flags."""

    def test_allow_unauthenticated_arg_parsing(self):
        """Verify --allow-unauthenticated flag is recognized."""
        args = parse_args("serve", "--http", "--allow-unauthenticated")
        assert args.http is True
        assert args.allow_unauthenticated is True

        args_default = parse_args("serve", "--http")
        assert args_default.http is True
        assert args_default.allow_unauthenticated is False

    @pytest.mark.asyncio
    async def test_serve_http_auto_generates_keys_when_missing(self, isolated_env, capsys):
        """When running HTTP mode without existing keys, keys and token must be generated."""
        config_path = isolated_env["config_file"]
        args = parse_args("--config", str(config_path), "serve", "--http", "--no-banner")

        with patch("magg.cli.MaggRunner") as mock_runner_cls:
            mock_runner = mock_runner_cls.return_value
            mock_runner.run_http = AsyncMock()

            result = await cmd_serve(args)
            assert result == 0

            config_manager = ConfigManager(str(config_path))
            auth_config = config_manager.load_auth_config()
            assert auth_config.bearer.private_key_exists is True
            assert auth_config.bearer.public_key_exists is True

            mock_runner.run_http.assert_awaited_once_with(host="localhost", port=8000)

            captured = capsys.readouterr()
            assert "AUTHENTICATION ENABLED FOR HTTP ACCESS" in captured.err

    @pytest.mark.asyncio
    async def test_serve_http_allow_unauthenticated_skips_generation(self, isolated_env, capsys):
        """When --allow-unauthenticated is provided, keys are not generated and a warning is printed."""
        config_path = isolated_env["config_file"]
        args = parse_args(
            "--config",
            str(config_path),
            "serve",
            "--http",
            "--allow-unauthenticated",
            "--no-banner",
        )

        with patch("magg.cli.MaggRunner") as mock_runner_cls:
            mock_runner = mock_runner_cls.return_value
            mock_runner.run_http = AsyncMock()

            result = await cmd_serve(args)
            assert result == 0

            config_manager = ConfigManager(str(config_path))
            auth_config = config_manager.load_auth_config()
            assert auth_config.bearer.private_key_exists is False

            captured = capsys.readouterr()
            assert "SECURITY WARNING: Running HTTP server without authentication!" in captured.err
