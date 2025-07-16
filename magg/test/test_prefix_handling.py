"""Test prefix and separator handling."""

import pytest
import os
from magg.settings import MaggConfig, ServerConfig
from magg.server.server import MaggServer
from fastmcp import Client


class TestPrefixHandling:
    """Test custom prefix and separator handling."""

    def test_prefix_separator_on_magg_config(self):
        """Test that prefix_sep is a configurable field on MaggConfig."""
        config = MaggConfig()
        assert hasattr(config, 'prefix_sep')
        assert config.prefix_sep == "_"  # Default value
        
        # Test it can be configured
        config2 = MaggConfig(prefix_sep="-")
        assert config2.prefix_sep == "-"

    def test_server_config_uses_separator(self):
        """Test that ServerConfig validation uses the separator."""
        # Valid prefix
        server = ServerConfig(name="test", source="test", prefix="myprefix")
        assert server.prefix == "myprefix"
        
        # Invalid prefix with underscore
        with pytest.raises(ValueError, match="cannot contain underscores"):
            ServerConfig(name="test", source="test", prefix="my_prefix")

    @pytest.mark.asyncio
    async def test_custom_self_prefix(self, tmp_path, monkeypatch):
        """Test that custom self_prefix is used correctly."""
        # Set custom prefix via environment
        monkeypatch.setenv("MAGG_SELF_PREFIX", "myapp")
        
        config_path = tmp_path / "config.json"
        server = MaggServer(config_path, enable_config_reload=False)
        
        # Check configuration
        assert server.self_prefix == "myapp"
        assert server.self_prefix_ == "myapp_"
        
        await server.setup()
        
        # Verify tools have the correct prefix
        async with Client(server.mcp) as client:
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]
            
            # All Magg tools should have myapp_ prefix
            myapp_tools = [t for t in tool_names if t.startswith("myapp_")]
            assert len(myapp_tools) > 0
            assert "myapp_list_servers" in tool_names
            assert "myapp_add_server" in tool_names
            assert "myapp_status" in tool_names
            
            # Should not have any magg_ tools
            magg_tools = [t for t in tool_names if t.startswith("magg_")]
            assert len(magg_tools) == 0

    def test_prefix_separator_consistency(self):
        """Test that prefix separator is used consistently."""
        # Create a server with default Magg config
        config = MaggConfig()
        assert config.self_prefix == "magg"
        assert config.prefix_sep == "_"
        
        # Server config validation should use the separator
        server1 = ServerConfig(name="test1", source="test", prefix="myprefix")
        assert server1.prefix == "myprefix"
        
        # Empty prefix is allowed
        server2 = ServerConfig(name="test2", source="test", prefix="")
        assert server2.prefix == ""
        
        # None prefix is allowed  
        server3 = ServerConfig(name="test3", source="test", prefix=None)
        assert server3.prefix is None