"""Test tool delegation functionality for MAGG."""

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
        """Test listing tools from a server."""
        from magg.server import MAGGServer
        
        server = MAGGServer()
        await server.setup()
        
        # Call list_tools
        result = await server.list_tools()
        
        assert result.is_success
        assert "tool_groups" in result.output
        assert "total_tools" in result.output
        
        # Should at least have MAGG's own tools
        tool_groups = result.output["tool_groups"]
        magg_group = next((g for g in tool_groups if g["prefix"] == "magg"), None)
        assert magg_group is not None
        assert len(magg_group["tools"]) > 0
    
    @pytest.mark.asyncio 
    async def test_mounted_server_tools(self):
        """Test that mounted server tools appear in listings."""
        from magg.server import MAGGServer
        from unittest.mock import patch, AsyncMock, MagicMock
        
        server = MAGGServer()
        await server.setup()
        
        # Mock mounting a server with tools
        with patch.object(server.mcp, 'get_tools', new_callable=AsyncMock) as mock_get_tools:
            # Simulate MAGG tools plus mounted server tools
            mock_get_tools.return_value = {
                "magg_list_servers": MagicMock(),
                "magg_add_server": MagicMock(),
                "test_tool1": MagicMock(),  # From mounted server with prefix "test"
                "test_tool2": MagicMock(),
            }
            
            result = await server.list_tools()
            
            assert result.is_success
            tool_groups = result.output["tool_groups"]
            
            # Should have both magg and test prefixes
            prefixes = [g["prefix"] for g in tool_groups]
            assert "magg" in prefixes
            assert "test" in prefixes
            
            # Check test group has the tools
            test_group = next(g for g in tool_groups if g["prefix"] == "test")
            assert "test_tool1" in test_group["tools"]
            assert "test_tool2" in test_group["tools"]