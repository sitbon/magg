"""Tests for MAGG_KIT_CHANGES_ONLY environment variable."""

import json
import os
import pytest
import pytest_asyncio
from pathlib import Path

from magg.server.server import MaggServer
from fastmcp.client import Client


class TestKitChangesOnly:
    """Test MAGG_KIT_CHANGES_ONLY environment variable functionality."""

    @pytest_asyncio.fixture
    async def config_path(self, tmp_path):
        """Create a temporary config path."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"servers": {}}))
        return config_path

    @pytest.mark.asyncio
    async def test_default_mode_all_tools_exposed(self, config_path):
        """Test that all tools are exposed by default (kit_changes_only=false)."""
        # Ensure environment variable is not set or is false
        os.environ.pop('MAGG_KIT_CHANGES_ONLY', None)

        server = MaggServer(str(config_path), enable_config_reload=False)

        async with server:
            async with Client(server.mcp) as client:
                tools = await client.list_tools()
                tool_names = {t.name for t in tools}

                # Verify both kit tools and management tools are present
                assert 'magg_load_kit' in tool_names, "Kit tools should be present"
                assert 'magg_unload_kit' in tool_names
                assert 'magg_list_kits' in tool_names
                assert 'magg_kit_info' in tool_names

                assert 'magg_add_server' in tool_names, "Management tools should be present"
                assert 'magg_remove_server' in tool_names
                assert 'magg_list_servers' in tool_names
                assert 'magg_status' in tool_names

                # Should have more than just kit tools
                assert len(tool_names) > 5, "Should have many tools in default mode"

    @pytest.mark.asyncio
    async def test_kit_changes_only_mode_enabled(self, config_path):
        """Test that only kit and view tools are exposed when MAGG_KIT_CHANGES_ONLY=true."""
        os.environ['MAGG_KIT_CHANGES_ONLY'] = 'true'

        try:
            server = MaggServer(str(config_path), enable_config_reload=False)

            async with server:
                async with Client(server.mcp) as client:
                    tools = await client.list_tools()
                    tool_names = {t.name for t in tools}

                    # Verify kit tools are present
                    assert 'magg_load_kit' in tool_names, "load_kit should be present"
                    assert 'magg_unload_kit' in tool_names, "unload_kit should be present"
                    assert 'magg_list_kits' in tool_names, "list_kits should be present"
                    assert 'magg_kit_info' in tool_names, "kit_info should be present"

                    # Verify view tools are present
                    assert 'magg_list_servers' in tool_names, "list_servers should be present"
                    assert 'magg_status' in tool_names, "status should be present"

                    # Verify modification tools are NOT present
                    assert 'magg_add_server' not in tool_names, "add_server should NOT be present"
                    assert 'magg_remove_server' not in tool_names, "remove_server should NOT be present"
                    assert 'magg_enable_server' not in tool_names, "enable_server should NOT be present"
                    assert 'magg_disable_server' not in tool_names, "disable_server should NOT be present"
                    assert 'magg_search_servers' not in tool_names, "search_servers should NOT be present"
                    assert 'magg_smart_configure' not in tool_names, "smart_configure should NOT be present"
                    assert 'magg_analyze_servers' not in tool_names, "analyze_servers should NOT be present"
                    assert 'magg_check' not in tool_names, "check should NOT be present"
                    assert 'magg_reload_config' not in tool_names, "reload_config should NOT be present"

                    # Proxy tool may still be present (it's registered by ProxyMCP)
                    # Only kit tools + view tools + proxy should be present
                    expected_tool_names = {
                        'magg_load_kit', 'magg_unload_kit', 'magg_list_kits', 'magg_kit_info',
                        'magg_list_servers', 'magg_status',
                        'proxy'
                    }
                    assert tool_names == expected_tool_names, f"Only kit and view tools should be present, got: {tool_names}"

        finally:
            os.environ.pop('MAGG_KIT_CHANGES_ONLY', None)

    @pytest.mark.asyncio
    async def test_kit_changes_only_mode_disabled(self, config_path):
        """Test that all tools are exposed when MAGG_KIT_CHANGES_ONLY=false."""
        os.environ['MAGG_KIT_CHANGES_ONLY'] = 'false'

        try:
            server = MaggServer(str(config_path), enable_config_reload=False)

            async with server:
                async with Client(server.mcp) as client:
                    tools = await client.list_tools()
                    tool_names = {t.name for t in tools}

                    # Verify both kit tools and management tools are present
                    assert 'magg_load_kit' in tool_names
                    assert 'magg_add_server' in tool_names

                    # Should have many tools
                    assert len(tool_names) > 5

        finally:
            os.environ.pop('MAGG_KIT_CHANGES_ONLY', None)

    @pytest.mark.asyncio
    async def test_kit_and_view_tools_functional_in_kit_changes_only_mode(self, tmp_path):
        """Test that kit and view tools are functional when MAGG_KIT_CHANGES_ONLY=true."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"servers": {}}))

        # Create a kit directory with a test kit
        kitd_path = tmp_path / "kit.d"
        kitd_path.mkdir()

        kit_path = kitd_path / "test-kit.json"
        kit_path.write_text(json.dumps({
            "name": "test-kit",
            "description": "Test kit for kit_changes_only mode",
            "servers": {
                "dummy-server": {
                    "source": "https://example.com",
                    "command": "echo",
                    "enabled": False
                }
            }
        }))

        os.environ['MAGG_KIT_CHANGES_ONLY'] = 'true'
        os.environ['MAGG_PATH'] = str(tmp_path)

        try:
            server = MaggServer(str(config_path), enable_config_reload=False)

            async with server:
                async with Client(server.mcp) as client:
                    # Test kit tools
                    result = await client.call_tool('magg_list_kits', {})
                    assert 'test-kit' in str(result.content), "Should be able to list kits"

                    result = await client.call_tool('magg_kit_info', {'name': 'test-kit'})
                    assert 'test-kit' in str(result.content), "Should be able to get kit info"

                    # Test view tools
                    result = await client.call_tool('magg_list_servers', {})
                    assert result.content is not None, "Should be able to list servers"

                    result = await client.call_tool('magg_status', {})
                    assert result.content is not None, "Should be able to get status"

        finally:
            os.environ.pop('MAGG_KIT_CHANGES_ONLY', None)
            os.environ.pop('MAGG_PATH', None)
