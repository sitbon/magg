"""Tests for configuration reload functionality."""
import asyncio
import json
import signal
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from magg.reload import ConfigReloader, ConfigChange, ServerChange
from magg.server.server import MaggServer
from magg.server.runner import MaggRunner
from magg.settings import MaggConfig, ServerConfig, ConfigManager


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file."""
    config_path = tmp_path / "config.json"
    config_data = {
        "servers": {
            "test-server": {
                "source": "https://example.com/test",
                "command": "echo",
                "args": ["test"],
                "enabled": True
            }
        }
    }
    config_path.write_text(json.dumps(config_data, indent=2))
    return config_path


class TestConfigReloader:
    """Test the ConfigReloader class."""

    @pytest.mark.asyncio
    async def test_detect_changes_add_server(self):
        """Test detecting when a server is added."""
        old_config = MaggConfig()
        new_config = MaggConfig()
        new_config.servers["new-server"] = ServerConfig(
            name="new-server",
            source="https://example.com/new",
            command="echo"
        )

        reloader = ConfigReloader(Path("/fake/path"), lambda x: None)
        change = reloader._detect_changes(old_config, new_config)

        assert change.has_changes
        assert len(change.server_changes) == 1
        assert change.server_changes[0].action == "add"
        assert change.server_changes[0].name == "new-server"

    @pytest.mark.asyncio
    async def test_detect_changes_remove_server(self):
        """Test detecting when a server is removed."""
        old_config = MaggConfig()
        old_config.servers["old-server"] = ServerConfig(
            name="old-server",
            source="https://example.com/old",
            command="echo"
        )
        new_config = MaggConfig()

        reloader = ConfigReloader(Path("/fake/path"), lambda x: None)
        change = reloader._detect_changes(old_config, new_config)

        assert change.has_changes
        assert len(change.server_changes) == 1
        assert change.server_changes[0].action == "remove"
        assert change.server_changes[0].name == "old-server"

    @pytest.mark.asyncio
    async def test_detect_changes_update_server(self):
        """Test detecting when a server is updated."""
        old_config = MaggConfig()
        old_config.servers["test-server"] = ServerConfig(
            name="test-server",
            source="https://example.com/test",
            command="echo",
            args=["old"]
        )

        new_config = MaggConfig()
        new_config.servers["test-server"] = ServerConfig(
            name="test-server",
            source="https://example.com/test",
            command="echo",
            args=["new"]
        )

        reloader = ConfigReloader(Path("/fake/path"), lambda x: None)
        change = reloader._detect_changes(old_config, new_config)

        assert change.has_changes
        assert len(change.server_changes) == 1
        assert change.server_changes[0].action == "update"
        assert change.server_changes[0].name == "test-server"

    @pytest.mark.asyncio
    async def test_detect_changes_enable_disable(self):
        """Test detecting when a server is enabled/disabled."""
        old_config = MaggConfig()
        old_config.servers["test-server"] = ServerConfig(
            name="test-server",
            source="https://example.com/test",
            command="echo",
            enabled=False
        )

        new_config = MaggConfig()
        new_config.servers["test-server"] = ServerConfig(
            name="test-server",
            source="https://example.com/test",
            command="echo",
            enabled=True
        )

        reloader = ConfigReloader(Path("/fake/path"), lambda x: None)
        change = reloader._detect_changes(old_config, new_config)

        assert change.has_changes
        assert len(change.server_changes) == 1
        assert change.server_changes[0].action == "enable"
        assert change.server_changes[0].name == "test-server"

    @pytest.mark.asyncio
    async def test_config_validation(self):
        """Test config validation allows duplicate prefixes."""
        config = MaggConfig()
        config.servers["server1"] = ServerConfig(
            name="server1",
            source="https://example.com/1",
            command="echo",
            prefix="test"
        )
        config.servers["server2"] = ServerConfig(
            name="server2",
            source="https://example.com/2",
            command="echo",
            prefix="test"  # Duplicate prefix is now allowed
        )

        reloader = ConfigReloader(Path("/fake/path"), lambda x: None)
        assert reloader._validate_config(config)  # Should pass validation

        # Test with None/empty prefixes
        config.servers["server3"] = ServerConfig(
            name="server3",
            source="https://example.com/3",
            command="echo",
            prefix=None
        )
        config.servers["server4"] = ServerConfig(
            name="server4",
            source="https://example.com/4",
            command="echo",
            prefix=None  # Duplicate None prefix is also allowed
        )
        assert reloader._validate_config(config)  # Should still pass

    @pytest.mark.asyncio
    async def test_reload_callback(self, temp_config_file):
        """Test that reload callback is called with changes."""
        callback_called = False
        received_change = None

        async def callback(change: ConfigChange):
            nonlocal callback_called, received_change
            callback_called = True
            received_change = change

        reloader = ConfigReloader(temp_config_file, callback)

        # Modify the config file
        new_config = {
            "servers": {
                "test-server": {
                    "source": "https://example.com/test",
                    "command": "echo",
                    "args": ["modified"],
                    "enabled": True
                }
            }
        }
        temp_config_file.write_text(json.dumps(new_config, indent=2))

        # Trigger reload
        await reloader.reload_config()

        assert callback_called
        assert received_change is not None
        assert received_change.has_changes


class TestServerReload:
    """Test server-level reload functionality."""

    @pytest.mark.asyncio
    async def test_server_manual_reload(self, temp_config_file):
        """Test manual config reload through server."""
        server = MaggServer(str(temp_config_file), enable_config_reload=False)

        # Mock the server manager's handle_config_reload
        with patch.object(server.server_manager, 'handle_config_reload') as mock_handler:
            success = await server.reload_config()

            assert success
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_server_auto_reload_works_in_readonly(self, temp_config_file):
        """Test that auto-reload works in read-only mode (external changes allowed)."""
        with patch.dict('os.environ', {'MAGG_READ_ONLY': 'true'}):
            server = MaggServer(str(temp_config_file))
            await server.setup()

            # Config manager should have reload manager set up
            assert server.server_manager.config_manager._reload_manager is not None

    @pytest.mark.asyncio
    async def test_reload_config_tool(self, temp_config_file):
        """Test the reload_config tool."""
        server = MaggServer(str(temp_config_file))

        with patch.object(server, 'reload_config', return_value=True) as mock_reload:
            result = await server.reload_config_tool()

            assert result.is_success
            assert "successfully" in result.output["message"]
            mock_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_reload_tool_disabled_when_auto_reload_false(self, temp_config_file):
        """Test that reload tool fails when auto_reload is false."""
        with patch.dict('os.environ', {'MAGG_AUTO_RELOAD': 'false'}):
            server = MaggServer(str(temp_config_file))
            response = await server.reload_config_tool()

            assert not response.is_success
            assert "Configuration reload is disabled" in response.errors[0]

    @pytest.mark.asyncio
    async def test_reload_tool_disabled_in_readonly_mode(self, temp_config_file):
        """Test that reload tool fails in read-only mode."""
        with patch.dict('os.environ', {'MAGG_READ_ONLY': 'true'}):
            server = MaggServer(str(temp_config_file))
            response = await server.reload_config_tool()

            assert not response.is_success
            assert "not allowed in read-only mode" in response.errors[0]


class TestRunnerSignalHandling:
    """Test signal handling for config reload."""

    @pytest.mark.skipif(not hasattr(signal, 'SIGHUP'), reason="SIGHUP not available")
    @pytest.mark.asyncio
    async def test_sighup_handling(self, temp_config_file):
        """Test that SIGHUP triggers config reload."""
        runner = MaggRunner(str(temp_config_file))

        # Mock the reload method
        with patch.object(runner._server, 'reload_config') as mock_reload:
            mock_reload.return_value = True

            # Setup signal handler
            runner._setup_signal_handlers()

            # Trigger SIGHUP
            runner._handle_reload_signal(signal.SIGHUP, None)

            # Check that reload event was set
            assert runner._reload_event.is_set()

            # Run the reload handler briefly
            reload_task = asyncio.create_task(runner._handle_reload_events())
            await asyncio.sleep(0.1)
            reload_task.cancel()
            try:
                await reload_task
            except asyncio.CancelledError:
                pass

            mock_reload.assert_called_once()


class TestConfigChangeDetection:
    """Test configuration change detection."""

    @pytest.mark.asyncio
    async def test_file_modification_triggers_reload(self, temp_config_file):
        """Test that file modification triggers reload."""
        reload_triggered = False

        async def callback(change: ConfigChange):
            nonlocal reload_triggered
            reload_triggered = True

        reloader = ConfigReloader(temp_config_file, callback)

        # Start watching with a short poll interval
        await reloader.start_watching(poll_interval=0.1)

        # Give it time to initialize
        await asyncio.sleep(0.2)

        # Modify the file
        config_data = json.loads(temp_config_file.read_text())
        config_data["servers"]["new-server"] = {
            "source": "https://example.com/new",
            "command": "echo",
            "args": ["new"]
        }
        temp_config_file.write_text(json.dumps(config_data, indent=2))

        # Wait for reload to trigger
        await asyncio.sleep(0.3)

        # Stop watching
        await reloader.stop_watching()

        assert reload_triggered


class TestConfigChangeSummary:
    """Test config change summary generation."""

    def test_change_summary(self):
        """Test generating a summary of changes."""
        change = ConfigChange(
            old_config=MaggConfig(),
            new_config=MaggConfig(),
            server_changes=[
                ServerChange(name="added", action="add"),
                ServerChange(name="removed", action="remove"),
                ServerChange(name="updated", action="update"),
                ServerChange(name="enabled", action="enable"),
                ServerChange(name="disabled", action="disable"),
            ]
        )

        summary = change.summarize()
        assert "+ added" in summary
        assert "- removed" in summary
        assert "~ updated" in summary
        assert "✓ enabled" in summary
        assert "✗ disabled" in summary


class TestMaggCheckResilience:
    """Test that magg_check handles failed servers gracefully."""

    @pytest.mark.asyncio
    async def test_check_with_failed_server(self, temp_config_file):
        """Test that check continues even when one server fails."""
        # Create config with multiple servers
        config_data = {
            "servers": {
                "good-server": {
                    "source": "https://example.com/good",
                    "command": "echo",
                    "args": ["good"],
                    "enabled": True
                },
                "bad-server": {
                    "source": "https://example.com/bad",
                    "command": "python",
                    "args": ["nonexistent.py"],
                    "enabled": True
                }
            }
        }
        temp_config_file.write_text(json.dumps(config_data, indent=2))

        server = MaggServer(str(temp_config_file))

        # Mock the mounted servers
        mock_good_client = AsyncMock()
        mock_good_client.list_tools.return_value = [{"name": "tool1"}]

        mock_bad_client = AsyncMock()
        mock_bad_client.list_tools.side_effect = Exception("Server session was closed unexpectedly")

        server.server_manager.mounted_servers = {
            "good-server": {"client": mock_good_client},
            "bad-server": {"client": mock_bad_client}
        }

        # Run check with default 0.5s timeout
        result = await server.check(action="report")

        # Should succeed overall
        assert result.is_success

        # Should have results for both servers
        assert "good-server" in result.output["results"]
        assert "bad-server" in result.output["results"]

        # Good server should be healthy
        assert result.output["results"]["good-server"]["status"] == "healthy"

        # Bad server should have error status
        assert result.output["results"]["bad-server"]["status"] == "error"
        assert "Server session was closed unexpectedly" in result.output["results"]["bad-server"]["reason"]


class TestProgrammaticChanges:
    """Test that programmatic config changes don't trigger reload loops."""

    @pytest.mark.asyncio
    async def test_save_config_ignores_own_changes(self, temp_config_file):
        """Test that saving config programmatically doesn't trigger a reload."""
        reload_count = 0

        async def callback(change: ConfigChange):
            nonlocal reload_count
            reload_count += 1

        # Create server with config reloader
        server = MaggServer(str(temp_config_file))
        await server.setup()

        # Replace the callback to count reloads
        if server.server_manager.config_manager._reload_manager:
            server.server_manager.config_manager._reload_manager._reload_callback = callback

        # Make a programmatic change (like disabling a server)
        config = server.config
        if "test-server" in config.servers:
            config.servers["test-server"].enabled = False
            server.server_manager.save_config(config)

        # Give time for file watcher to potentially trigger
        await asyncio.sleep(0.5)

        # Should not have triggered a reload
        assert reload_count == 0, "Programmatic config save should not trigger reload"
