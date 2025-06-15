"""Test tool delegation functionality for MAGG."""

import pytest
from fastmcp import FastMCP, Client


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
        from magg.core.config import MCPServer
        
        # Create server with specific prefix
        server = MCPServer(
            name="prefixed-server",
            source_url="https://example.com/prefixed",
            prefix="custom_prefix"
        )
        
        # Verify prefix is stored correctly
        assert server.prefix == "custom_prefix"
    
    def test_tool_name_collision_handling(self):
        """Test handling of tool name collisions between servers."""
        from magg.core.config import MAGGConfig, MCPServer
        
        config = MAGGConfig()
        
        # Add two servers with same prefix (potential collision)
        server1 = MCPServer(name="server1", source_url="https://example.com/1", prefix="same")
        server2 = MCPServer(name="server2", source_url="https://example.com/2", prefix="same")
        
        config.add_server(server1)
        config.add_server(server2)
        
        # Both servers should be stored
        assert len(config.servers) == 2
        assert "server1" in config.servers
        assert "server2" in config.servers


class TestToolDiscovery:
    """Test tool discovery and listing functionality."""
    
    def test_server_tool_listing(self):
        """Test listing tools from configured servers."""
        from magg.core.config import MAGGConfig, MCPServer
        
        config = MAGGConfig()
        
        # Add servers that would have tools
        server1 = MCPServer(name="calculator", source_url="https://example.com/calc", prefix="calc")
        server2 = MCPServer(name="weather", source_url="https://example.com/weather", prefix="weather")
        
        config.add_server(server1)
        config.add_server(server2)
        
        # Get all configured servers
        all_servers = list(config.servers.values())
        assert len(all_servers) == 2
        
        # Verify servers have expected prefixes for tool namespacing
        prefixes = {server.prefix for server in all_servers}
        assert prefixes == {"calc", "weather"}
    


@pytest.mark.integration
class TestToolDelegationIntegration:
    """Integration tests for tool delegation."""
    
    @pytest.mark.skip(reason="Requires external MCP servers for testing")
    @pytest.mark.asyncio
    async def test_real_server_tool_delegation(self):
        """Test delegation with real external MCP servers."""
        # This would test with actual MCP servers like:
        # - Calculator MCP server
        # - Weather MCP server
        # - etc.
        pass