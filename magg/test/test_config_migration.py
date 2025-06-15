"""Test configuration functionality and migrations."""

import pytest
import tempfile
import json
from pathlib import Path

from magg.core.config import ConfigManager, MCPSource, MCPServer, MAGGConfig


class TestConfigMigration:
    """Test configuration structure and functionality."""
    
    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_path = Path(f.name)
        yield config_path
        if config_path.exists():
            config_path.unlink()
    
    def test_new_config_structure(self, temp_config_file):
        """Test creating and using new config structure."""
        config_manager = ConfigManager(str(temp_config_file))
        config = config_manager.load_config()
        
        # Test adding a source with new structure
        new_source = MCPSource(
            url="https://github.com/example/weather-mcp",
            name="test-weather"
        )
        
        config.add_source(new_source)
        
        # Verify source was added
        assert len(config.sources) == 1
        assert "https://github.com/example/weather-mcp" in config.sources
        assert config.sources["https://github.com/example/weather-mcp"].name == "test-weather"
        
        # Test adding a server for this source
        new_server = MCPServer(
            name="weather-server",
            source_url="https://github.com/example/weather-mcp",
            prefix="weather",
            command=["npx", "weather-mcp-server"],
            notes="Test weather MCP server"
        )
        
        config.add_server(new_server)
        
        # Verify server was added
        assert len(config.servers) == 1
        assert "weather-server" in config.servers
        assert config.servers["weather-server"].source_url == "https://github.com/example/weather-mcp"
        assert config.servers["weather-server"].prefix == "weather"
    
    def test_sources_by_url_lookup(self):
        """Test finding sources by URL."""
        config = MAGGConfig()
        
        # Add multiple sources
        source1 = MCPSource(url="https://github.com/example/weather-mcp", name="weather1")
        source2 = MCPSource(url="https://github.com/example/weather-mcp", name="weather2")
        source3 = MCPSource(url="https://github.com/different/repo", name="other")
        
        config.add_source(source1)
        config.add_source(source2)  # Same URL, different name - should replace
        config.add_source(source3)
        
        # Should only have 2 sources (weather2 replaced weather1)
        assert len(config.sources) == 2
        assert config.sources["https://github.com/example/weather-mcp"].name == "weather2"
        assert config.sources["https://github.com/different/repo"].name == "other"
    
    def test_server_source_relationship(self):
        """Test relationship between servers and sources."""
        config = MAGGConfig()
        
        # Add source
        source = MCPSource(url="https://github.com/example/weather-mcp", name="weather")
        config.add_source(source)
        
        # Add multiple servers for same source
        server1 = MCPServer(name="weather-dev", source_url="https://github.com/example/weather-mcp", prefix="weather_dev")
        server2 = MCPServer(name="weather-prod", source_url="https://github.com/example/weather-mcp", prefix="weather_prod")
        
        config.add_server(server1)
        config.add_server(server2)
        
        # Test getting servers for source
        servers_for_source = config.get_servers_for_source("https://github.com/example/weather-mcp")
        assert len(servers_for_source) == 2
        server_names = {s.name for s in servers_for_source}
        assert server_names == {"weather-dev", "weather-prod"}
        
        # Test removing source removes associated servers
        config.remove_source("https://github.com/example/weather-mcp")
        assert len(config.sources) == 0
        assert len(config.servers) == 0
    
    def test_save_and_reload_config(self, temp_config_file):
        """Test saving config and reloading maintains structure."""
        config_manager = ConfigManager(str(temp_config_file))
        
        # Create config with data
        config = MAGGConfig()
        source = MCPSource(url="https://github.com/example/weather-mcp", name="weather")
        server = MCPServer(
            name="weather-server",
            source_url="https://github.com/example/weather-mcp",
            prefix="weather",
            command=["npx", "weather-mcp-server"],
            env={"API_KEY": "test123"},
            working_dir="/tmp/weather",
            notes="Weather server with API key"
        )
        
        config.add_source(source)
        config.add_server(server)
        
        # Save config
        success = config_manager.save_config(config)
        assert success is True
        
        # Load config
        loaded_config = config_manager.load_config()
        
        # Verify structure preserved
        assert len(loaded_config.sources) == 1
        assert len(loaded_config.servers) == 1
        
        loaded_source = loaded_config.sources["https://github.com/example/weather-mcp"]
        assert loaded_source.name == "weather"
        
        loaded_server = loaded_config.servers["weather-server"]
        assert loaded_server.source_url == "https://github.com/example/weather-mcp"
        assert loaded_server.prefix == "weather"
        assert loaded_server.command == ["npx", "weather-mcp-server"]
        assert loaded_server.env == {"API_KEY": "test123"}
        assert loaded_server.working_dir == "/tmp/weather"
        assert loaded_server.notes == "Weather server with API key"