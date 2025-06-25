"""Test in-memory Magg server functionality via FastMCPTransport."""
import json
import sys
import pytest
from fastmcp import Client
from fastmcp.client import FastMCPTransport

from magg.server import MaggServer


@pytest.mark.asyncio
async def test_in_memory_basic_tools(tmp_path):
    """Test basic Magg tools work via in-memory transport."""
    # Create config in temp directory
    config_path = tmp_path / ".magg" / "config.json"
    config_path.parent.mkdir()

    # Create server
    server = MaggServer(str(config_path))
    await server.setup()

    # Create in-memory client
    client = Client(FastMCPTransport(server.mcp))

    async with client:
        # Test listing tools
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}

        # Should have Magg management tools
        assert "magg_add_server" in tool_names
        assert "magg_list_servers" in tool_names
        assert "magg_remove_server" in tool_names
        assert "proxy" in tool_names

        # Test listing servers (should be empty)
        result = await client.call_tool("magg_list_servers", {})
        assert len(result) == 1
        assert result[0].type == "text"
        assert "[]" in result[0].text  # Empty list


@pytest.mark.asyncio
async def test_in_memory_server_management(tmp_path):
    """Test adding and managing servers via in-memory transport."""
    config_path = tmp_path / ".magg" / "config.json"
    config_path.parent.mkdir()

    server = MaggServer(str(config_path))
    await server.setup()

    client = Client(FastMCPTransport(server.mcp))

    async with client:
        # Add a test server
        result = await client.call_tool("magg_add_server", {
            "name": "test-server",
            "source": "https://example.com/test",
            "command": "echo test",  # Full command string
            "enable": False  # Don't try to actually mount
        })

        assert len(result) == 1
        assert "server_added" in result[0].text

        # List servers
        result = await client.call_tool("magg_list_servers", {})
        assert len(result) == 1
        response = json.loads(result[0].text)
        assert response["errors"] is None
        servers = response["output"]
        assert len(servers) == 1
        assert servers[0]["name"] == "test-server"
        assert servers[0]["enabled"] is False

        # Remove server
        result = await client.call_tool("magg_remove_server", {
            "name": "test-server"
        })
        assert "server_removed" in result[0].text


@pytest.mark.asyncio
async def test_in_memory_proxy_tool(tmp_path):
    """Test proxy tool works via in-memory transport."""
    config_path = tmp_path / ".magg" / "config.json"
    config_path.parent.mkdir()

    server = MaggServer(str(config_path))
    await server.setup()

    client = Client(FastMCPTransport(server.mcp))

    async with client:
        # Use proxy to list tools
        result = await client.call_tool("proxy", {
            "action": "list",
            "type": "tool"
        })

        # Should return embedded resource with tool list
        assert len(result) == 1
        assert result[0].type == "resource"
        assert result[0].resource.mimeType == "application/json"

        # Check annotations
        assert hasattr(result[0], "annotations")
        assert result[0].annotations.proxyAction == "list"
        assert result[0].annotations.proxyType == "tool"


@pytest.mark.asyncio
async def test_in_memory_tool_call_requires_setup(tmp_path):
    """Test that external server tools require setup() to be called."""
    config_path = tmp_path / ".magg" / "config.json"
    config_path.parent.mkdir()

    # Create a simple test MCP server script
    test_server = tmp_path / "test_server.py"
    test_server.write_text("""
import sys
from fastmcp import FastMCP

mcp = FastMCP("test-server")

@mcp.tool()
async def test_add(a: int, b: int) -> str:
    return f"Result: {a + b}"

if __name__ == "__main__":
    mcp.run()
""")

    # Create config with the test server
    config_data = {
        "servers": {
            "test": {
                "name": "test",
                "source": str(tmp_path),
                "prefix": "test",
                "command": sys.executable,
                "args": [str(test_server)],
                "enabled": True
            }
        }
    }
    config_path.write_text(json.dumps(config_data))

    # Create server WITHOUT calling setup()
    server = MaggServer(str(config_path))
    client = Client(FastMCPTransport(server.mcp))

    async with client:
        # List tools - should NOT have test server tools
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        assert "test_test_add" not in tool_names

        # Try to call the tool - should fail
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("test_test_add", {"a": 5, "b": 3})
        assert "Unknown tool" in str(exc_info.value) or "not found" in str(exc_info.value)

    # Now call setup()
    await server.setup()

    # Create new client after setup
    client_after = Client(FastMCPTransport(server.mcp))

    async with client_after:
        # List tools - should NOW have test server tools
        tools = await client_after.list_tools()
        tool_names = {tool.name for tool in tools}
        assert "test_test_add" in tool_names

        # Call the tool - should work
        result = await client_after.call_tool("test_test_add", {"a": 5, "b": 3})
        assert len(result) == 1
        assert result[0].text == "Result: 8"
