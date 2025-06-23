"""Basic functionality tests for MAGG using pytest."""

import pytest
from fastmcp import Client
from magg.server import MAGGServer
import tempfile
from pathlib import Path


class TestMAGGBasicFunctionality:
    """Test basic MAGG functionality."""

    @pytest.mark.asyncio
    async def test_basic_setup_and_tools(self, tmp_path):
        """Test MAGG setup and tool availability."""
        config_path = tmp_path / "config.json"
        server = MAGGServer(config_path)
        await server.setup()

        # Check for core MAGG tools
        expected_tools = ["magg_list_servers", "magg_add_server", "magg_status", "magg_check"]

        async with Client(server.mcp) as client:
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]

            for tool in expected_tools:
                assert tool in tool_names

    # list_tools was removed from the server
    # @pytest.mark.asyncio
    # async def test_magg_list_tools(self):
    #     """Test MAGG list tools functionality."""
    #     server = MAGGServer()
    #     await server.setup()
    #
    #     async with Client(server.mcp) as client:
    #         result = await client.call_tool("magg_list_tools", {})
    #         assert len(result) > 0
    #         assert hasattr(result[0], 'text')
    #         assert isinstance(result[0].text, str)

    @pytest.mark.asyncio
    async def test_list_servers(self, tmp_path):
        """Test listing servers."""
        config_path = tmp_path / "config.json"
        server = MAGGServer(config_path)
        await server.setup()

        async with Client(server.mcp) as client:
            result = await client.call_tool("magg_list_servers", {})
            assert len(result) > 0
            assert hasattr(result[0], 'text')
            assert isinstance(result[0].text, str)


class TestMAGGServerManagement:
    """Test server management functionality."""

    @pytest.mark.asyncio
    async def test_add_server(self, tmp_path):
        """Test adding a server."""
        config_path = tmp_path / "config.json"
        server = MAGGServer(config_path)
        await server.setup()

        import time
        unique_id = str(int(time.time()))

        async with Client(server.mcp) as client:
            # Add a server directly
            server_name = f"testserver{unique_id}"
            result = await client.call_tool("magg_add_server", {
                "name": server_name,
                "source": f"https://github.com/example/test-{unique_id}",
                "prefix": "test",
                "command": "echo test"
            })

            assert len(result) > 0
            assert hasattr(result[0], 'text')

            # Verify server was added by listing
            result = await client.call_tool("magg_list_servers", {})
            assert server_name in result[0].text


class TestMAGGServerSearch:
    """Test server search functionality."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_search_servers(self, tmp_path):
        """Test server search (requires internet)."""
        config_path = tmp_path / "config.json"
        server = MAGGServer(config_path)
        await server.setup()

        async with Client(server.mcp) as client:
            try:
                result = await client.call_tool("magg_search_servers", {
                    "query": "filesystem",
                    "limit": 3
                })
                assert len(result) > 0
                assert hasattr(result[0], 'text')
            except Exception as e:
                pytest.skip(f"Search test failed (requires internet): {e}")
