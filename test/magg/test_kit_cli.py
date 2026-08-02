"""Tests for kit CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from magg.cli import cmd_kit, create_parser
from magg.kit import KitConfig
from magg.settings import ConfigManager, MaggConfig, ServerConfig


class TestKitCLI:
    """Test kit CLI commands."""

    @pytest.fixture
    def mock_args(self):
        """Create mock args object."""
        args = MagicMock()
        args.config = None
        args.json = False
        return args

    @pytest.fixture
    def mock_kit_manager(self):
        """Create mock kit manager with test kits."""
        manager = MagicMock()

        # Mock discover_kits
        manager.discover_kits.return_value = {
            "test-kit": Path("/mock/kit.d/test-kit.json"),
            "empty-kit": Path("/mock/kit.d/empty-kit.json"),
        }

        # Mock load_kit
        def mock_load_kit(path):
            if "test-kit" in str(path):
                kit = KitConfig(
                    name="test-kit",
                    description="Test kit for unit tests",
                    author="Test Author",
                    version="1.0.0",
                    keywords=["test", "example"],
                    links={"homepage": "https://example.com"},
                    servers={
                        "test-server": ServerConfig(
                            name="test-server",
                            source="https://example.com/test",
                            command="echo",
                            args=["test"],
                            notes="Test server",
                        )
                    },
                )
                return kit
            elif "empty-kit" in str(path):
                return KitConfig(name="empty-kit", description="Empty kit")
            return None

        manager.load_kit.side_effect = mock_load_kit
        manager.kitd_paths = [Path("/mock/kit.d")]

        return manager

    @pytest.mark.asyncio
    async def test_kit_list(self, mock_args, mock_kit_manager, capsys):
        """Test kit list command."""
        mock_args.kit_action = "list"

        # Patch KitManager at the cli module level where it's used
        with patch("magg.cli.KitManager", return_value=mock_kit_manager):
            with patch("magg.cli.ConfigManager"):
                await cmd_kit(mock_args)

        captured = capsys.readouterr()
        # All output goes to stderr for consistency
        assert "Available kits (2)" in captured.err
        assert "test-kit: Test kit for unit tests" in captured.err
        assert "empty-kit: Empty kit" in captured.err

    @pytest.mark.asyncio
    async def test_kit_list_empty(self, mock_args, capsys):
        """Test kit list when no kits found."""
        mock_args.kit_action = "list"

        manager = MagicMock()
        manager.discover_kits.return_value = {}
        manager.kitd_paths = [Path("/mock/kit.d")]

        with patch("magg.cli.KitManager", return_value=manager):
            with patch("magg.cli.ConfigManager"):
                await cmd_kit(mock_args)

        captured = capsys.readouterr()
        assert "No kits found" in captured.err
        assert "Search paths:" in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_success(self, mock_args, mock_kit_manager, capsys):
        """Test successful kit load."""
        mock_args.kit_action = "load"
        mock_args.name = "test-kit"
        mock_args.enable = True

        # Mock config
        config = MaggConfig()
        config.kits = {}
        config.servers = {}

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = True

        with patch("magg.cli.KitManager", return_value=mock_kit_manager):
            with patch("magg.cli.ConfigManager", return_value=mock_config_instance):
                await cmd_kit(mock_args)

        # Check that server was added
        assert "test-server" in config.servers
        assert config.servers["test-server"].enabled is True
        assert "test-kit" in config.kits

        # Check output
        captured = capsys.readouterr()
        assert "Added 1 servers from kit" in captured.err
        assert "test-server (enabled)" in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_no_enable(self, mock_args, mock_kit_manager, capsys):
        """Test kit load with --no-enable flag."""
        mock_args.kit_action = "load"
        mock_args.name = "test-kit"
        mock_args.enable = False

        # Mock config
        config = MaggConfig()
        config.kits = {}
        config.servers = {}

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = True

        with patch("magg.cli.KitManager", return_value=mock_kit_manager):
            with patch("magg.cli.ConfigManager", return_value=mock_config_instance):
                await cmd_kit(mock_args)

        # Check that server was added but disabled
        assert "test-server" in config.servers
        assert config.servers["test-server"].enabled is False

        # Check output
        captured = capsys.readouterr()
        assert "test-server (disabled)" in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_not_found(self, mock_args, mock_kit_manager, capsys):
        """Test kit load with non-existent kit."""
        mock_args.kit_action = "load"
        mock_args.name = "nonexistent-kit"

        with patch("magg.cli.KitManager", return_value=mock_kit_manager):
            with patch("magg.cli.ConfigManager"):
                result = await cmd_kit(mock_args)
                assert result == 1

        captured = capsys.readouterr()
        assert "Kit 'nonexistent-kit' not found" in captured.err
        assert "Available kits: test-kit, empty-kit" in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_skip_existing(self, mock_args, mock_kit_manager, capsys):
        """Test kit load skips existing servers."""
        mock_args.kit_action = "load"
        mock_args.name = "test-kit"
        mock_args.enable = True

        # Mock config with existing server
        config = MaggConfig()
        config.kits = {}
        config.servers = {
            "test-server": ServerConfig(name="test-server", source="https://different.com", command="different")
        }

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = True

        with patch("magg.cli.KitManager", return_value=mock_kit_manager):
            with patch("magg.cli.ConfigManager", return_value=mock_config_instance):
                await cmd_kit(mock_args)

        # Check that existing server was not overwritten, but gained kit membership
        assert config.servers["test-server"].source == "https://different.com"
        assert "test-kit" in config.servers["test-server"].kits

        # Check output
        captured = capsys.readouterr()
        assert "Updated kit membership for 1 existing servers" in captured.err
        assert "test-server" in captured.err

    @pytest.mark.asyncio
    async def test_kit_info(self, mock_args, mock_kit_manager, capsys):
        """Test kit info command."""
        mock_args.kit_action = "info"
        mock_args.name = "test-kit"

        # Since KitManager is imported inside the function, patch at the module level
        with patch("magg.cli.KitManager", return_value=mock_kit_manager):
            with patch("magg.cli.ConfigManager"):
                await cmd_kit(mock_args)

        captured = capsys.readouterr()
        assert "Kit: test-kit" in captured.err
        assert "Description: Test kit for unit tests" in captured.err
        assert "Author: Test Author" in captured.err
        assert "Version: 1.0.0" in captured.err
        assert "Keywords: test, example" in captured.err
        assert "homepage: https://example.com" in captured.err
        assert "Servers (1):" in captured.err
        assert "test-server" in captured.err
        assert "Test server" in captured.err

    @pytest.mark.asyncio
    async def test_kit_info_not_found(self, mock_args, mock_kit_manager, capsys):
        """Test kit info with non-existent kit."""
        mock_args.kit_action = "info"
        mock_args.name = "nonexistent-kit"

        with patch("magg.cli.KitManager", return_value=mock_kit_manager):
            with patch("magg.cli.ConfigManager"):
                result = await cmd_kit(mock_args)
                assert result == 1

        captured = capsys.readouterr()
        assert "Kit 'nonexistent-kit' not found" in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_empty_kit(self, mock_args, mock_kit_manager, capsys):
        """Test loading a kit with no servers."""
        mock_args.kit_action = "load"
        mock_args.name = "empty-kit"
        mock_args.enable = True

        # Mock config
        config = MaggConfig()
        config.kits = {}
        config.servers = {}

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = True

        with patch("magg.cli.KitManager", return_value=mock_kit_manager):
            with patch("magg.cli.ConfigManager", return_value=mock_config_instance):
                await cmd_kit(mock_args)

        # Check output
        captured = capsys.readouterr()
        assert "Kit 'empty-kit' contains no servers" in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_save_failure(self, mock_args, mock_kit_manager, capsys):
        """Test kit load when config save fails."""
        mock_args.kit_action = "load"
        mock_args.name = "test-kit"
        mock_args.enable = True

        # Mock config
        config = MaggConfig()
        config.kits = {}
        config.servers = {}

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = False  # Simulate save failure

        with patch("magg.cli.KitManager", return_value=mock_kit_manager):
            with patch("magg.cli.ConfigManager", return_value=mock_config_instance):
                result = await cmd_kit(mock_args)
                assert result == 1

        captured = capsys.readouterr()
        assert "Failed to save configuration" in captured.err


class TestKitUnloadCLI:
    """Test kit unload CLI command with real kit files and config."""

    @pytest.fixture
    def kit_env(self, tmp_path, monkeypatch):
        """Isolated MAGG_PATH with two kits sharing a server."""
        magg_dir = tmp_path / ".magg"
        kitd = magg_dir / "kit.d"
        kitd.mkdir(parents=True)

        (kitd / "alpha.json").write_text(
            json.dumps(
                {
                    "description": "Alpha kit",
                    "servers": {
                        "shared": {"source": "https://example.com/shared", "command": "echo shared"},
                        "alpha-only": {"source": "https://example.com/a", "command": "echo a"},
                    },
                }
            )
        )
        (kitd / "beta.json").write_text(
            json.dumps(
                {
                    "description": "Beta kit",
                    "servers": {
                        "shared": {"source": "https://example.com/shared", "command": "echo shared"},
                        "beta-only": {"source": "https://example.com/b", "command": "echo b"},
                    },
                }
            )
        )

        monkeypatch.setenv("MAGG_PATH", str(magg_dir))
        monkeypatch.delenv("MAGG_CONFIG_PATH", raising=False)
        monkeypatch.delenv("MAGG_READ_ONLY", raising=False)
        return magg_dir / "config.json"

    async def run_kit_cmd(self, config_path, *argv) -> int:
        args = create_parser().parse_args(["--config", str(config_path), "kit", *argv])
        return await cmd_kit(args) or 0

    def load_config(self, config_path):
        return ConfigManager(config_path).load_config()

    @pytest.mark.asyncio
    async def test_unload_removes_exclusive_servers(self, kit_env, capsys):
        assert await self.run_kit_cmd(kit_env, "load", "alpha") == 0
        assert await self.run_kit_cmd(kit_env, "unload", "alpha", "--force") == 0

        config = self.load_config(kit_env)
        assert "alpha" not in config.kits
        assert config.servers == {}

        captured = capsys.readouterr()
        assert "unloaded successfully" in captured.err

    @pytest.mark.asyncio
    async def test_unload_preserves_shared_servers(self, kit_env, capsys):
        assert await self.run_kit_cmd(kit_env, "load", "alpha") == 0
        assert await self.run_kit_cmd(kit_env, "load", "beta") == 0

        # Loading beta must register kit membership on the shared server
        config = self.load_config(kit_env)
        assert sorted(config.servers["shared"].kits) == ["alpha", "beta"]

        assert await self.run_kit_cmd(kit_env, "unload", "alpha", "--force") == 0

        config = self.load_config(kit_env)
        assert "alpha" not in config.kits
        assert "beta" in config.kits
        assert "alpha-only" not in config.servers
        assert config.servers["shared"].kits == ["beta"]
        assert "beta-only" in config.servers

    @pytest.mark.asyncio
    async def test_load_already_loaded(self, kit_env, capsys):
        assert await self.run_kit_cmd(kit_env, "load", "alpha") == 0
        result = await self.run_kit_cmd(kit_env, "load", "alpha")
        assert result == 1

        captured = capsys.readouterr()
        assert "Kit 'alpha' is already loaded" in captured.err

    @pytest.mark.asyncio
    async def test_load_persists_membership_for_manually_added_server(self, kit_env, capsys):
        """Regression: kit membership on a pre-existing server must survive save/load.

        Servers added via 'magg server add' have no 'kits' key in config.json; the
        membership added by 'kit load' must be persisted anyway (exclude_unset).
        """
        from magg.cli import cmd_server

        args = create_parser().parse_args(
            ["--config", str(kit_env), "server", "add", "shared", "https://example.com/shared", "--command", "echo hi"]
        )
        assert await cmd_server(args) == 0

        assert await self.run_kit_cmd(kit_env, "load", "alpha") == 0

        captured = capsys.readouterr()
        assert "Updated kit membership for 1 existing servers" in captured.err

        # Membership must survive a round-trip through config.json
        config = self.load_config(kit_env)
        assert config.servers["shared"].kits == ["alpha"]

        # And unload must now treat the server as belonging to the kit
        assert await self.run_kit_cmd(kit_env, "unload", "alpha", "--force") == 0
        config = self.load_config(kit_env)
        assert "shared" not in config.servers

    @pytest.mark.asyncio
    async def test_unload_not_loaded(self, kit_env, capsys):
        result = await self.run_kit_cmd(kit_env, "unload", "alpha")
        assert result == 1

        captured = capsys.readouterr()
        assert "Kit 'alpha' is not loaded" in captured.err

    @pytest.mark.asyncio
    async def test_unload_cancelled_without_force(self, kit_env, capsys):
        assert await self.run_kit_cmd(kit_env, "load", "alpha") == 0

        with patch("magg.cli.confirm_action", return_value=False):
            result = await self.run_kit_cmd(kit_env, "unload", "alpha")
        assert result == 0

        config = self.load_config(kit_env)
        assert "alpha" in config.kits
        assert "alpha-only" in config.servers

        captured = capsys.readouterr()
        assert "Unload cancelled" in captured.err

    @pytest.mark.asyncio
    async def test_kit_list_json(self, kit_env, capsys):
        assert await self.run_kit_cmd(kit_env, "load", "alpha") == 0
        capsys.readouterr()

        assert await self.run_kit_cmd(kit_env, "list", "--json") == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["kits"]["alpha"]["loaded"] is True
        assert data["kits"]["beta"]["loaded"] is False
        assert sorted(data["kits"]["alpha"]["servers"]) == ["alpha-only", "shared"]
