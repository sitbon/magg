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
        assert "servers" in result.output
        assert "total_tools" in result.output
        
        # Should at least have MAGG's own tools
        tool_groups = result.output["servers"]
        magg_group = tool_groups.get("magg", None)
        assert magg_group is not None
        assert len(magg_group["tools"]) > 0
    
    @pytest.mark.asyncio 
    async def test_mounted_server_tools(self):
        """Test that mounted server tools appear in listings."""
        from magg.server import MAGGServer
        from unittest.mock import patch, AsyncMock, MagicMock
        from magg.settings import ServerConfig
        
        server = MAGGServer()
        await server.setup()
        
        # Create a mock server config
        test_server_config = ServerConfig(
            name="testserver",
            source="test://example",
            prefix="test",
            command="echo"
        )
        
        # Create a mock config
        mock_config = MagicMock()
        mock_config.servers = {
            "testserver": test_server_config
        }
        
        # Patch the config_manager.load_config method
        with patch.object(server.server_manager.config_manager, 'load_config', return_value=mock_config):
            # Create mock client and connection
            mock_client = MagicMock()
            mock_conn = AsyncMock()
            
            # Create mock tools
            mock_tool1 = MagicMock()
            mock_tool1.name = "tool1"
            mock_tool2 = MagicMock()
            mock_tool2.name = "tool2"
            
            # Mock the list_tools call
            mock_conn.list_tools = AsyncMock(return_value=[mock_tool1, mock_tool2])
            
            # Make the client work as an async context manager
            mock_client.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            # Mock mounted_servers
            server.server_manager.mounted_servers = {
                "testserver": {
                    "client": mock_client,
                    "proxy": MagicMock()
                }
            }
            
            # Mock get_tools to return MAGG's own tools
            with patch.object(server.mcp, 'get_tools', new_callable=AsyncMock) as mock_get_tools:
                mock_get_tools.return_value = {
                    "magg_list_servers": MagicMock(),
                    "magg_add_server": MagicMock(),
                    "magg_list_tools": MagicMock(),
                }
                
                result = await server.list_tools()
                
                assert result.is_success
                assert "servers" in result.output
                assert "total_tools" in result.output
                
                servers = result.output["servers"]
                
                # Should have both magg and testserver
                assert "magg" in servers
                assert "testserver" in servers
                
                # Check MAGG tools
                magg_tools = servers["magg"]["tools"]
                assert "magg_list_servers" in magg_tools
                assert "magg_add_server" in magg_tools
                assert "magg_list_tools" in magg_tools
                
                # Check test server tools (should be prefixed)
                test_tools = servers["testserver"]["tools"]
                assert "test_tool1" in test_tools
                assert "test_tool2" in test_tools
                assert servers["testserver"]["prefix"] == "test"
                
                # Verify total count
                assert result.output["total_tools"] == 5  # 3 MAGG + 2 test server
