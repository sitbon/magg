"""Test configuration functionality."""

import pytest
import tempfile
import json
from pathlib import Path

from magg.settings import ConfigManager, ServerConfig, MaggConfig


class TestConfigStructure:
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

        # Test adding servers
        server1 = ServerConfig(
            name="weatherserver",
            source="https://github.com/example/weather-mcp",
            command="npx",
            args=["weather-mcp"],
            prefix="weather"
        )

        server2 = ServerConfig(
            name="filesystemserver",
            source="https://github.com/example/filesystem-mcp",
            uri="http://localhost:8080"
        )

        config.add_server(server1)
        config.add_server(server2)

        # Save and reload
        assert config_manager.save_config(config) is True

        loaded_config = config_manager.load_config()
        assert len(loaded_config.servers) == 2

        # Verify servers loaded correctly
        weather = loaded_config.servers["weatherserver"]
        assert weather.source == "https://github.com/example/weather-mcp"
        assert weather.command == "npx"
        assert weather.prefix == "weather"

        filesystem = loaded_config.servers["filesystemserver"]
        assert filesystem.uri == "http://localhost:8080"
        assert filesystem.prefix == "filesystemserver"  # Default prefix

    def test_config_serialization_format(self, temp_config_file):
        """Test the actual JSON format of saved config."""
        config_manager = ConfigManager(str(temp_config_file))
        config = MaggConfig()

        # Add a server with all fields
        server = ServerConfig(
            name="testserver",
            source="https://github.com/test/test-mcp",
            prefix="test",
            command="python",
            args=["-m", "test_mcp"],
            env={"TEST_VAR": "value"},
            working_dir="/tmp/test",
            notes="Test server for unit tests",
            enabled=False
        )

        config.add_server(server)
        config_manager.save_config(config)

        # Read raw JSON
        with open(temp_config_file, 'r') as f:
            raw_data = json.load(f)

        # Check structure
        assert "servers" in raw_data
        assert "testserver" in raw_data["servers"]

        server_data = raw_data["servers"]["testserver"]
        assert "name" not in server_data  # Name left out and used as a key
        assert server_data["source"] == "https://github.com/test/test-mcp"
        assert server_data["prefix"] == "test"
        assert server_data["command"] == "python"
        assert server_data["args"] == ["-m", "test_mcp"]
        assert server_data["env"] == {"TEST_VAR": "value"}
        assert server_data["working_dir"] == "/tmp/test"
        assert server_data["notes"] == "Test server for unit tests"
        assert server_data["enabled"] is False

    def test_minimal_server_config(self, temp_config_file):
        """Test minimal server configuration."""
        config_manager = ConfigManager(str(temp_config_file))
        config = MaggConfig()

        # Minimal server - just name and source
        server = ServerConfig(
            name="minimal",
            source="https://example.com"
        )

        config.add_server(server)
        config_manager.save_config(config)

        # Reload and check defaults
        loaded_config = config_manager.load_config()
        minimal = loaded_config.servers["minimal"]

        assert minimal.name == "minimal"
        assert minimal.source == "https://example.com"
        assert minimal.prefix == "minimal"  # Defaults to name
        assert minimal.enabled is True  # Default enabled
        assert minimal.command is None
        assert minimal.args is None
        assert minimal.uri is None
        assert minimal.env is None
        assert minimal.working_dir is None
        assert minimal.notes is None

    def test_environment_variable_override(self):
        """Test that environment variables can override settings."""
        import os

        # Set environment variable
        os.environ["MAGG_LOG_LEVEL"] = "DEBUG"

        try:
            config = MaggConfig()
            assert config.log_level == "DEBUG"
        finally:
            # Clean up
            del os.environ["MAGG_LOG_LEVEL"]

    def test_invalid_server_in_config(self, temp_config_file):
        """Test handling of servers with names that need prefix generation."""
        # Write config with server that needs prefix adjustment
        invalid_config = {
            "servers": {
                "valid": {
                    "source": "https://example.com"
                },
                "123invalid": {
                    "source": "https://example.com"
                }
            }
        }

        with open(temp_config_file, 'w') as f:
            json.dump(invalid_config, f)

        config_manager = ConfigManager(str(temp_config_file))
        config = config_manager.load_config()

        # Both servers should load now with auto-generated prefixes
        assert len(config.servers) == 2
        assert "valid" in config.servers
        assert "123invalid" in config.servers

        # Check that the problematic server got a valid prefix
        assert config.servers["123invalid"].name == "123invalid"
        assert config.servers["123invalid"].prefix == "srv123invalid"  # Auto-generated prefix
