"""Tests for MAGG configuration management."""

import pytest
import tempfile
import json
from pathlib import Path

from magg.core.config import ConfigManager, MCPSource, MCPServer, MAGGConfig


class TestMCPSource:
    """Test MCPSource functionality."""
    
    def test_source_creation_with_name(self):
        """Test creating a source with explicit name."""
        source = MCPSource(url="https://github.com/example/repo", name="test-source")
        assert source.url == "https://github.com/example/repo"
        assert source.name == "test-source"
    
    def test_source_auto_name_from_github(self):
        """Test auto-generating name from GitHub URL."""
        source = MCPSource(url="https://github.com/example/weather-mcp")
        assert source.name == "weather-mcp"
    
    def test_source_auto_name_from_npm(self):
        """Test auto-generating name from NPM URL."""
        source = MCPSource(url="https://www.npmjs.com/package/calculator-mcp")
        assert source.name == "calculator-mcp"
    
    def test_source_auto_name_fallback(self):
        """Test fallback name generation."""
        source = MCPSource(url="https://example.com/some/path")
        assert source.name == "example_com"


class TestMCPServer:
    """Test MCPServer functionality."""
    
    def test_server_creation(self):
        """Test creating a server configuration."""
        server = MCPServer(
            name="test-server",
            source_url="https://github.com/example/repo",
            prefix="test",
            command=["./server"],
            notes="Test server"
        )
        assert server.name == "test-server"
        assert server.source_url == "https://github.com/example/repo"
        assert server.prefix == "test"
        assert server.command == ["./server"]
        assert server.notes == "Test server"
    
    def test_server_auto_prefix(self):
        """Test auto-setting prefix to name."""
        server = MCPServer(
            name="weather",
            source_url="https://github.com/example/repo"
            # Don't pass prefix, should auto-set to name
        )
        # The prefix should be auto-set to name in __post_init__
        assert server.prefix == "weather"


class TestMAGGConfig:
    """Test MAGGConfig functionality."""
    
    def test_config_creation(self):
        """Test creating empty configuration."""
        config = MAGGConfig()
        assert len(config.sources) == 0
        assert len(config.servers) == 0
    
    def test_add_source(self):
        """Test adding a source."""
        config = MAGGConfig()
        source = MCPSource(url="https://github.com/example/repo", name="test")
        
        config.add_source(source)
        assert len(config.sources) == 1
        assert config.sources["https://github.com/example/repo"] == source
    
    def test_add_server(self):
        """Test adding a server."""
        config = MAGGConfig()
        server = MCPServer(name="test", source_url="https://github.com/example/repo")
        
        config.add_server(server)
        assert len(config.servers) == 1
        assert config.servers["test"] == server
    
    def test_remove_source_with_servers(self):
        """Test removing a source also removes associated servers."""
        config = MAGGConfig()
        
        # Add source
        source = MCPSource(url="https://github.com/example/repo", name="test")
        config.add_source(source)
        
        # Add servers for this source
        server1 = MCPServer(name="server1", source_url="https://github.com/example/repo")
        server2 = MCPServer(name="server2", source_url="https://github.com/example/repo")
        config.add_server(server1)
        config.add_server(server2)
        
        # Remove source
        removed = config.remove_source("https://github.com/example/repo")
        assert removed is True
        assert len(config.sources) == 0
        assert len(config.servers) == 0  # Servers should be removed too
    
    
    def test_get_servers_for_source(self):
        """Test getting servers for a specific source."""
        config = MAGGConfig()
        
        source1_url = "https://github.com/example/repo1"
        source2_url = "https://github.com/example/repo2"
        
        server1 = MCPServer(name="server1", source_url=source1_url)
        server2 = MCPServer(name="server2", source_url=source1_url)
        server3 = MCPServer(name="server3", source_url=source2_url)
        
        config.add_server(server1)
        config.add_server(server2)
        config.add_server(server3)
        
        source1_servers = config.get_servers_for_source(source1_url)
        assert len(source1_servers) == 2
        assert all(s.source_url == source1_url for s in source1_servers)


class TestConfigManager:
    """Test ConfigManager functionality."""
    
    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_path = Path(f.name)
        yield config_path
        if config_path.exists():
            config_path.unlink()
    
    def test_load_empty_config(self, temp_config_file):
        """Test loading configuration when file doesn't exist."""
        # Remove the file so it doesn't exist
        temp_config_file.unlink()
        
        manager = ConfigManager(str(temp_config_file))
        config = manager.load_config()
        
        assert isinstance(config, MAGGConfig)
        assert len(config.sources) == 0
        assert len(config.servers) == 0
    
    def test_save_and_load_config(self, temp_config_file):
        """Test saving and loading configuration."""
        manager = ConfigManager(str(temp_config_file))
        
        # Create config with data
        config = MAGGConfig()
        source = MCPSource(url="https://github.com/example/repo", name="test")
        server = MCPServer(name="test-server", source_url="https://github.com/example/repo")
        config.add_source(source)
        config.add_server(server)
        
        # Save config
        success = manager.save_config(config)
        assert success is True
        assert temp_config_file.exists()
        
        # Load config
        loaded_config = manager.load_config()
        assert len(loaded_config.sources) == 1
        assert len(loaded_config.servers) == 1
        assert loaded_config.sources["https://github.com/example/repo"].name == "test"
        assert loaded_config.servers["test-server"].name == "test-server"
    
    def test_save_load_complex_config(self, temp_config_file):
        """Test saving and loading complex configuration."""
        manager = ConfigManager(str(temp_config_file))
        
        config = MAGGConfig()
        
        # Add source
        source = MCPSource(url="https://github.com/example/weather", name="weather")
        config.add_source(source)
        
        # Add server with all fields
        server = MCPServer(
            name="weather-server",
            source_url="https://github.com/example/weather",
            prefix="weather",
            command=["./weather-server"],
            env={"API_KEY": "test"},
            working_dir="/tmp",
            notes="Weather server with API key"
        )
        config.add_server(server)
        
        # Save and reload
        manager.save_config(config)
        loaded_config = manager.load_config()
        
        loaded_server = loaded_config.servers["weather-server"]
        assert loaded_server.name == "weather-server"
        assert loaded_server.prefix == "weather"
        assert loaded_server.command == ["./weather-server"]
        assert loaded_server.env == {"API_KEY": "test"}
        assert loaded_server.working_dir == "/tmp"
        assert loaded_server.notes == "Weather server with API key"