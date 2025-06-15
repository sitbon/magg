"""Basic functionality tests for MAGG using pytest."""

import pytest
from fastmcp import Client
from magg.server import mcp, setup_magg


class TestMAGGBasicFunctionality:
    """Test basic MAGG functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_setup_and_tools(self):
        """Test MAGG setup and tool availability."""
        await setup_magg()
        
        # Check for core MAGG tools
        expected_tools = ["magg_list_servers", "magg_add_source", "magg_add_server", "magg_list_tools"]
        
        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]
            
            for tool in expected_tools:
                assert tool in tool_names
    
    @pytest.mark.asyncio
    async def test_magg_list_tools(self):
        """Test MAGG list tools functionality."""
        await setup_magg()
        
        async with Client(mcp) as client:
            result = await client.call_tool("magg_list_tools", {})
            assert len(result) > 0
            assert hasattr(result[0], 'text')
            assert isinstance(result[0].text, str)
    
    @pytest.mark.asyncio
    async def test_list_servers(self):
        """Test listing servers."""
        await setup_magg()
        
        async with Client(mcp) as client:
            result = await client.call_tool("magg_list_servers", {})
            assert len(result) > 0
            assert hasattr(result[0], 'text')
            assert isinstance(result[0].text, str)


class TestMAGGServerManagement:
    """Test server management functionality."""
    
    @pytest.mark.asyncio
    async def test_add_source_and_server(self):
        """Test adding a source and then a server."""
        await setup_magg()
        
        import time
        unique_id = str(int(time.time()))
        
        async with Client(mcp) as client:
            # First add a source with unique URL
            source_url = f"https://github.com/example/test-server-{unique_id}"
            result = await client.call_tool("magg_add_source", {
                "url": source_url,
                "name": f"test-server-{unique_id}"
            })
            assert len(result) > 0
            # Should either succeed or already exist
            assert "✅" in result[0].text or "⚠️" in result[0].text
            
            # Then add a server that references this source
            server_name = f"test_server_{unique_id}"
            result = await client.call_tool("magg_add_server", {
                "name": server_name,
                "source_url": source_url,
                "prefix": "test",
                "command": "echo test"
            })
            
            assert len(result) > 0
            assert hasattr(result[0], 'text')
            
            # Verify server was added by listing
            result = await client.call_tool("magg_list_servers", {})
            assert server_name in result[0].text


class TestMAGGSourceSearch:
    """Test source search functionality."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_search_sources(self):
        """Test source search (requires internet)."""
        await setup_magg()
        
        async with Client(mcp) as client:
            try:
                result = await client.call_tool("magg_search_sources", {
                    "query": "filesystem",
                    "limit": 3
                })
                assert len(result) > 0
                assert hasattr(result[0], 'text')
            except Exception as e:
                pytest.skip(f"Search test failed (requires internet): {e}")