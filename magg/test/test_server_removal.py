"""Test server removal behavior to debug the double-remove issue."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from magg.server.server import MaggServer
from magg.server.manager import ServerManager
from magg.settings import ConfigManager


class TestServerRemoval:
    """Test server removal to understand the double-remove issue."""

    @pytest.fixture
    def temp_config(self):
        """Create a temporary config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "self_prefix": "test",
                "servers": {
                    "test1": {
                        "source": "test-source",
                        "prefix": "t1",
                        "command": "echo",
                        "args": ["test"]
                    },
                    "test2": {
                        "source": "test-source-2",
                        "prefix": "t2",
                        "command": "echo",
                        "args": ["test2"]
                    }
                }
            }
            json.dump(config_data, f)
            return Path(f.name)

    @pytest.fixture
    def config_manager(self, temp_config):
        """Create a config manager with temp config."""
        return ConfigManager(str(temp_config))

    @pytest.fixture
    def magg_server(self, temp_config):
        """Create a Magg server instance."""
        server = MaggServer(str(temp_config))
        # Don't mount servers during init for testing
        return server

    def test_config_remove_server(self, config_manager):
        """Test that remove_server correctly updates the config."""
        # Load initial config
        config = config_manager.load_config()
        assert "test1" in config.servers
        assert "test2" in config.servers

        # Remove a server
        result = config.remove_server("test1")
        assert result is True
        assert "test1" not in config.servers
        assert "test2" in config.servers

        # Save and reload
        config_manager.save_config(config)
        reloaded = config_manager.load_config()
        assert "test1" not in reloaded.servers
        assert "test2" in reloaded.servers

    @pytest.mark.asyncio
    async def test_remove_server_flow(self, magg_server, config_manager):
        """Test the full remove_server flow to understand the issue."""
        # Initial state
        config = config_manager.load_config()
        assert "test1" in config.servers

        # First removal attempt
        response = await magg_server.remove_server("test1")
        assert response.errors is None
        assert response.output["action"] == "server_removed"

        # Check config file directly
        with open(config_manager.config_path) as f:
            file_data = json.load(f)
        assert "test1" not in file_data["servers"], "Server should be removed from file after first call"

        # Check what list_servers returns
        list_response = await magg_server.list_servers()
        # list_servers returns a list directly as output
        server_names = [s["name"] for s in list_response.output]
        assert "test1" not in server_names, "Server should not appear in list after removal"

        # Try removing again (should fail)
        response2 = await magg_server.remove_server("test1")
        assert response2.errors is not None
        assert any("not found" in error for error in response2.errors)

    @pytest.mark.asyncio
    async def test_unmount_server_config_loading(self, config_manager):
        """Test the unmount_server behavior with config loading."""
        # Create a minimal ServerManager
        server_manager = ServerManager(config_manager)

        # Add a server to mounted_servers
        server_manager.mounted_servers["test1"] = {
            'proxy': None,
            'client': None
        }

        # Load config and verify test1 exists
        config = config_manager.load_config()
        assert "test1" in config.servers

        # Remove from config but don't save yet
        config.remove_server("test1")
        assert "test1" not in config.servers

        # Call unmount_server - it will reload config from disk
        result = await server_manager.unmount_server("test1")

        # Since we didn't save, unmount should still find the server in reloaded config
        assert result is True
        assert "test1" not in server_manager.mounted_servers

    @pytest.mark.asyncio
    async def test_race_condition_simulation(self, config_manager):
        """Simulate the race condition between remove and unmount."""
        server_manager = ServerManager(config_manager)

        # Simulate the exact flow from remove_server
        config = server_manager.config
        initial_servers = list(config.servers.keys())
        assert "test1" in initial_servers
        assert len(initial_servers) == 2  # test1 and test2

        # Remove from in-memory config
        removed = config.remove_server("test1")
        assert removed is True
        assert "test1" not in config.servers
        assert "test2" in config.servers  # test2 should still be there
        assert len(config.servers) == 1

        # Before saving, unmount_server loads config from disk
        config_in_unmount = server_manager.config
        assert "test1" in config_in_unmount.servers, "Config on disk still has test1"
        assert len(config_in_unmount.servers) == 2  # Both test1 and test2 still on disk

        # This demonstrates the race condition - unmount sees the old config!
        # Now save the config
        server_manager.save_config(config)

        # Check the file directly
        import json
        with open(config_manager.config_path) as f:
            file_data = json.load(f)

        # After save, file should only have test2
        assert "test1" not in file_data["servers"]
        assert "test2" in file_data["servers"]
        assert len(file_data["servers"]) == 1

        # After save, loading should not have test1
        config_after_save = server_manager.config
        assert "test1" not in config_after_save.servers
        assert "test2" in config_after_save.servers
        assert len(config_after_save.servers) == 1


@pytest.mark.asyncio
async def test_with_real_stdio_server(tmp_path):
    """Integration test with actual stdio mounting/unmounting."""
    # Create config in temp directory
    config_path = tmp_path / ".magg" / "config.json"
    config_path.parent.mkdir(exist_ok=True)

    # Write initial config
    config_data = {
        "servers": {
            "echo_test": {
                "source": "test",
                "prefix": "echo",
                "command": "python",
                "args": ["-c", "print('Hello from echo server'); exit(0)"]
            }
        }
    }

    with open(config_path, 'w') as f:
        json.dump(config_data, f)

    # Create server with this config
    server = MaggServer(str(config_path))

    # Mount servers
    await server.server_manager.mount_all_enabled()

    # Verify server is there
    list_resp = await server.list_servers()
    assert any(s["name"] == "echo_test" for s in list_resp.output)

    # Remove server
    remove_resp = await server.remove_server("echo_test")
    assert remove_resp.errors is None

    # Verify it's gone
    list_resp2 = await server.list_servers()
    assert not any(s["name"] == "echo_test" for s in list_resp2.output)

    # Try removing again - should fail
    remove_resp2 = await server.remove_server("echo_test")
    assert remove_resp2.errors is not None


if __name__ == "__main__":
    # Run the race condition test to demonstrate the issue
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "servers": {
                "test1": {
                    "source": "test-source",
                    "prefix": "t1",
                    "command": "echo",
                    "args": ["test"]
                }
            }
        }
        json.dump(config_data, f)
        config_path = Path(f.name)

    config_manager = ConfigManager(str(config_path))

    print("Running race condition simulation...")
    asyncio.run(TestServerRemoval().test_race_condition_simulation(config_manager))

    # Cleanup
    config_path.unlink()
