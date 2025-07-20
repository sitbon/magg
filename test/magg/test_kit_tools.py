"""Tests for kit management tools in MaggServer."""

import json
import os
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from magg.server.server import MaggServer
from magg.server.response import MaggResponse
from magg.kit import KitConfig
from magg.settings import ServerConfig


class TestKitTools:
    """Test kit management tools in MaggServer."""

    @pytest_asyncio.fixture
    async def server(self, tmp_path):
        """Create a MaggServer instance with mocked components."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"servers": {}}))

        server = MaggServer(str(config_path), enable_config_reload=False)
        await server.__aenter__()

        yield server

        await server.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_load_kit_success(self, server, tmp_path):
        """Test successfully loading a kit."""
        # Create kit file
        kitd_path = tmp_path / "kit.d"
        kitd_path.mkdir()

        kit_path = kitd_path / "test-kit.json"
        kit_path.write_text(json.dumps({
            "name": "test-kit",
            "description": "Test kit",
            "servers": {
                "test-server": {
                    "source": "https://test.com",
                    "command": "python",
                    "enabled": True
                }
            }
        }))

        # Mock kit manager
        server.kit_manager._kits = {}
        server.kit_manager.kitd_paths = [kitd_path]

        # Mock server mounting
        server.server_manager.mount_server = AsyncMock(return_value=True)
        server.server_manager.mounted_servers = {}

        # Mock save_config to return True
        server.save_config = MagicMock(return_value=True)

        # Load kit
        response = await server.load_kit("test-kit")

        assert response.is_success is True
        assert response.output["action"] == "kit_loaded"
        assert response.output["kit"] == "test-kit"
        assert "Kit 'test-kit' loaded successfully" in response.output["message"]

        # Verify server was mounted
        server.server_manager.mount_server.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_kit_already_loaded(self, server):
        """Test loading a kit that's already loaded."""
        # Mock config with existing kit
        from magg.settings import KitInfo
        server.config.kits = {"existing-kit": KitInfo(name="existing-kit", source="file")}

        # Mock the kit manager to return the already loaded error
        server.kit_manager.load_kit_to_config = MagicMock(
            return_value=(False, "Kit 'existing-kit' is already loaded")
        )

        response = await server.load_kit("existing-kit")

        assert response.is_error is True
        assert "already loaded" in response.errors[0]

    @pytest.mark.asyncio
    async def test_load_kit_not_found(self, server):
        """Test loading a kit that doesn't exist."""
        # Mock empty kit discovery
        server.kit_manager.discover_kits = MagicMock(return_value={})

        response = await server.load_kit("nonexistent-kit")

        assert response.is_error is True
        assert "not found" in response.errors[0]

    @pytest.mark.asyncio
    async def test_unload_kit_success(self, server):
        """Test successfully unloading a kit."""
        # Create a persistent config object
        mock_config = MagicMock()
        from magg.settings import KitInfo
        mock_config.kits = {"test-kit": KitInfo(name="test-kit", source="file")}
        mock_config.servers = {
            "server1": ServerConfig(
                name="server1",
                source="https://server1.com",
                kits=["test-kit"]
            ),
            "server2": ServerConfig(
                name="server2",
                source="https://server2.com",
                kits=["test-kit", "other-kit"]
            )
        }

        # Patch config_manager.load_config to return the same object each time
        server.server_manager.config_manager.load_config = MagicMock(return_value=mock_config)

        # Mock server manager
        server.server_manager.mounted_servers = {"server1": {}, "server2": {}}
        server.server_manager.unmount_server = AsyncMock(return_value=True)

        # Mock save_config to return True
        server.save_config = MagicMock(return_value=True)

        # Mock kit manager to simulate server1 being removed
        def mock_unload_kit(kit_name, config):
            # Simulate removing server1 from config
            if "server1" in config.servers:
                del config.servers["server1"]
            # Update server2's kit list
            if "server2" in config.servers:
                config.servers["server2"].kits = ["other-kit"]
            if kit_name in config.kits:
                del config.kits[kit_name]
            return True, "Kit 'test-kit' unloaded successfully. Removed servers: server1"

        server.kit_manager.unload_kit_from_config = MagicMock(side_effect=mock_unload_kit)

        # Unload kit
        response = await server.unload_kit("test-kit")

        assert response.is_success is True
        assert response.output["action"] == "kit_unloaded"
        assert response.output["kit"] == "test-kit"

        # Verify server1 was unmounted (only in test-kit)
        server.server_manager.unmount_server.assert_called_once_with("server1")

    @pytest.mark.asyncio
    async def test_unload_kit_not_loaded(self, server):
        """Test unloading a kit that's not loaded."""
        server.config.kits = {}
        server.kit_manager.unload_kit_from_config = MagicMock(
            return_value=(False, "Kit 'nonexistent' is not loaded")
        )

        response = await server.unload_kit("nonexistent")

        assert response.is_error is True
        assert "not loaded" in response.errors[0]

    @pytest.mark.asyncio
    async def test_list_kits(self, server):
        """Test listing all kits."""
        # Mock kit listing
        mock_kits = {
            "kit1": {
                "loaded": True,
                "path": "/path/to/kit1.json",
                "description": "First kit",
                "author": "Author 1",
                "version": "1.0.0",
                "keywords": ["test"],
                "servers": ["server1", "server2"]
            },
            "kit2": {
                "loaded": False,
                "path": "/path/to/kit2.json",
                "description": "Second kit",
                "author": "Author 2",
                "version": "2.0.0",
                "keywords": ["example"],
                "servers": ["server3"]
            }
        }

        server.kit_manager.list_all_kits = MagicMock(return_value=mock_kits)

        response = await server.list_kits()

        assert response.is_success is True
        assert response.output["kits"] == mock_kits
        assert response.output["summary"]["total"] == 2
        assert response.output["summary"]["loaded"] == 1
        assert response.output["summary"]["available"] == 1

    @pytest.mark.asyncio
    async def test_kit_info_success(self, server):
        """Test getting kit information."""
        mock_info = {
            "loaded": True,
            "name": "test-kit",
            "description": "Test kit",
            "author": "Test Author",
            "version": "1.0.0",
            "keywords": ["test"],
            "links": {"homepage": "https://test.com"},
            "servers": {
                "test-server": {
                    "source": "https://test-server.com",
                    "command": "python"
                }
            }
        }

        server.kit_manager.get_kit_details = MagicMock(return_value=mock_info)

        response = await server.kit_info("test-kit")

        assert response.is_success is True
        assert response.output == mock_info

    @pytest.mark.asyncio
    async def test_kit_info_not_found(self, server):
        """Test getting info for nonexistent kit."""
        server.kit_manager.get_kit_details = MagicMock(return_value=None)

        response = await server.kit_info("nonexistent")

        assert response.is_error is True
        assert "not found" in response.errors[0]

    @pytest.mark.asyncio
    async def test_kit_tools_error_handling(self, server):
        """Test error handling in kit tools."""
        # Test load_kit error
        server.kit_manager.load_kit_to_config = MagicMock(
            side_effect=Exception("Test error")
        )

        response = await server.load_kit("test-kit")
        assert response.is_error is True
        assert "Failed to load kit: Test error" in response.errors[0]

        # Test unload_kit error
        server.kit_manager.unload_kit_from_config = MagicMock(
            side_effect=Exception("Unload error")
        )

        response = await server.unload_kit("test-kit")
        assert response.is_error is True
        assert "Failed to unload kit: Unload error" in response.errors[0]

        # Test list_kits error
        server.kit_manager.list_all_kits = MagicMock(
            side_effect=Exception("List error")
        )

        response = await server.list_kits()
        assert response.is_error is True
        assert "Failed to list kits: List error" in response.errors[0]

        # Test kit_info error
        server.kit_manager.get_kit_details = MagicMock(
            side_effect=Exception("Info error")
        )

        response = await server.kit_info("test-kit")
        assert response.is_error is True
        assert "Failed to get kit info: Info error" in response.errors[0]


class TestKitManagerWithServer:
    """Test kit manager initialization in MaggServer."""

    @pytest.mark.asyncio
    async def test_server_initializes_kit_manager(self, tmp_path):
        """Test that MaggServer properly initializes kit manager."""
        # Create config with kits
        config_path = tmp_path / "config.json"
        config_data = {
            "servers": {},
            "kits": ["kit1", "kit2"]
        }
        config_path.write_text(json.dumps(config_data))

        # Create kit files
        kitd_path = tmp_path / "kit.d"
        kitd_path.mkdir()

        kit1_path = kitd_path / "kit1.json"
        kit1_path.write_text(json.dumps({
            "name": "kit1",
            "description": "Kit 1",
            "servers": {}
        }))

        # Use MAGG_PATH environment variable to set kit search path
        with patch.dict(os.environ, {"MAGG_PATH": str(tmp_path)}):
            server = MaggServer(str(config_path), enable_config_reload=False)

            # Verify kit manager exists
            assert hasattr(server, "kit_manager")
            assert server.kit_manager is not None

            # Verify kits were loaded
            loaded_kits = server.kit_manager.kits
            assert "kit1" in loaded_kits

    @pytest.mark.asyncio
    async def test_kit_tools_registered(self, tmp_path):
        """Test that kit tools are properly registered."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"servers": {}}))

        server = MaggServer(str(config_path), enable_config_reload=False)
        await server.__aenter__()

        # Get registered tools
        tools = await server.mcp.get_tools()

        # Tools is a list of tool names (strings) in FastMCP
        # Verify kit tools are registered
        assert "magg_load_kit" in tools
        assert "magg_unload_kit" in tools
        assert "magg_list_kits" in tools
        assert "magg_kit_info" in tools

        await server.__aexit__(None, None, None)
