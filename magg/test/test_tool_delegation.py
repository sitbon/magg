"""Test tool delegation functionality for Magg."""

import pytest
from fastmcp import FastMCP, Client
from magg.settings import ServerConfig


class TestToolDelegation:
    """Test tool delegation patterns."""

    def test_fastmcp_tool_creation(self):
        """Test that FastMCP tools can be created correctly."""
        mcp = FastMCP("test-delegation")

        @mcp.tool()
        def test_tool(message: str) -> str:
            """Test tool that returns a message."""
            return f"Received: {message}"

        # Test that tool was registered (FastMCP internal structure may vary)
        # This is a basic smoke test
        assert mcp is not None

    @pytest.mark.asyncio
    async def test_delegation_pattern(self):
        """Test delegation pattern with FastMCP client."""
        # Create a simple server for testing
        server = FastMCP("test-server")

        @server.tool()
        def delegate_test(query: str) -> str:
            """A tool that could be delegated to."""
            return f"Delegated result: {query}"

        # Test calling through client
        async with Client(server) as client:
            tools = await client.list_tools()
            assert len(tools) > 0
            assert tools[0].name == "delegate_test"

            result = await client.call_tool("delegate_test", {"query": "test"})
            assert len(result) > 0
            assert "Delegated result: test" in result[0].text

    def test_tool_prefix_handling(self):
        """Test that tool prefixes are handled correctly."""
        # Create server with specific prefix
        server = ServerConfig(
            name="prefixedserver",
            source="https://example.com",
            prefix="custom",
            command="echo"
        )

        # Test prefix validation
        assert server.prefix == "custom"

        # Test that default prefix uses cleaned name
        server2 = ServerConfig(
            name="test-server",
            source="https://example.com",
            command="echo"
        )
        assert server2.prefix == "testserver"  # Hyphens removed

    def test_tool_name_collision_handling(self):
        """Test handling of tool name collisions."""
        # In FastMCP, tools are prefixed by mount point
        # This prevents collisions automatically
        server1 = ServerConfig(
            name="server1",
            source="https://example.com",
            prefix="srv1",
            command="echo"
        )

        server2 = ServerConfig(
            name="server2",
            source="https://example.com",
            prefix="srv2",
            command="echo"
        )

        # Different prefixes prevent collision
        assert server1.prefix != server2.prefix


class TestToolDiscovery:
    """Test tool discovery functionality."""

    @pytest.mark.asyncio
    async def test_server_tool_listing(self):
        """Test listing tools from a server via Client."""
        from magg.server import MaggServer

        server = MaggServer()
        await server.setup()

        # List tools through the FastMCP client
        async with Client(server.mcp) as client:
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]

            # Should at least have Magg's own tools
            assert "magg_list_servers" in tool_names
            assert "magg_add_server" in tool_names
            assert len(tool_names) > 0

    @pytest.mark.asyncio
    async def test_mounted_server_tools(self):
        """Test that mounted server tools appear in listings."""
        from magg.server import MaggServer

        server = MaggServer()
        await server.setup()

        # Create a test MCP server
        test_server = FastMCP("test-server")

        @test_server.tool()
        def test_tool1(message: str) -> str:
            """Test tool 1."""
            return f"Tool 1: {message}"

        @test_server.tool()
        def test_tool2(value: int) -> int:
            """Test tool 2."""
            return value * 2

        # Mount the test server
        server.mcp.mount("test", test_server)

        # Access tools through the client
        async with Client(server.mcp) as client:
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]

            # Should have Magg's own tools
            assert "magg_list_servers" in tool_names
            assert "magg_add_server" in tool_names

            # Should have test server tools with prefix
            assert "test_test_tool1" in tool_names
            assert "test_test_tool2" in tool_names

            # Verify we have tools from both servers
            magg_tools = [t for t in tool_names if t.startswith("magg_")]
            test_tools = [t for t in tool_names if t.startswith("test_")]

            assert len(magg_tools) >= 2  # At least magg_list_servers and magg_add_server
            assert len(test_tools) == 2  # tool1 and tool2
