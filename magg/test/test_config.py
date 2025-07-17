"""Tests for Magg configuration management."""

import os
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from magg.settings import ConfigManager, ServerConfig, MaggConfig


class TestServerConfig:
    """Test ServerConfig functionality."""

    def test_server_creation_basic(self):
        """Test creating a basic server config."""
        server = ServerConfig(
            name="testserver",
            source="https://github.com/example/repo",
            prefix="testserver",
            command="python",
            args=["server.py"]
        )
        assert server.name == "testserver"
        assert server.source == "https://github.com/example/repo"
        assert server.command == "python"
        assert server.args == ["server.py"]
        assert server.prefix == "testserver"
        assert server.enabled is True  # Default enabled

    def test_server_with_custom_prefix(self):
        """Test server with custom prefix."""
        server = ServerConfig(
            name="myserver",
            source="https://github.com/example/repo",
            prefix="custom"
        )
        assert server.prefix == "custom"

    def test_server_name_validation(self):
        """Test that server names can be anything and prefix defaults to None."""
        # Any name is now valid - prefix defaults to None
        server1 = ServerConfig(name="valid", source="test")
        assert server1.prefix is None

        server2 = ServerConfig(name="valid123", source="test")
        assert server2.prefix is None

        server3 = ServerConfig(name="valid-name", source="test")
        assert server3.prefix is None

        # Names that would have been invalid before are now accepted
        server4 = ServerConfig(name="123invalid", source="test")
        assert server4.prefix is None

        server5 = ServerConfig(name="invalid!", source="test")
        assert server5.prefix is None

        server6 = ServerConfig(name="@namespace/package", source="test")
        assert server6.prefix is None

    def test_server_prefix_validation(self):
        """Test server prefix validation."""
        # Valid prefixes
        ServerConfig(name="test", source="test", prefix="validprefix")

        # Invalid prefixes - no underscores allowed
        with pytest.raises(ValueError, match="cannot contain underscores"):
            ServerConfig(name="test", source="test", prefix="invalid_prefix")

        # Invalid prefixes - must be identifier
        with pytest.raises(ValueError, match="must be a valid Python identifier"):
            ServerConfig(name="test", source="test", prefix="123invalid")



class TestMaggConfig:
    """Test MaggConfig functionality."""

    def test_config_defaults(self):
        """Test default configuration values."""
        # Remove MAGG env vars that might be set in container
        env = os.environ.copy()
        if 'MAGG_LOG_LEVEL' in env:
            del env['MAGG_LOG_LEVEL']
        if 'MAGG_CONFIG_PATH' in env:
            del env['MAGG_CONFIG_PATH']

        with patch.dict('os.environ', env, clear=True):
            config = MaggConfig()
            # config_path is now None by default, use get_config_path() for actual path
            assert config.config_path is None
            assert config.get_config_path() == Path.cwd() / ".magg" / "config.json"
            assert config.log_level is None, "Default log level should be None"
            assert config.servers == {}
            # Test default path includes project root, home, and contrib paths
            assert len(config.path) >= 3
            assert config.path[0] == Path.cwd() / ".magg"
            assert config.path[1] == Path.home() / ".magg"

    def test_get_script_paths(self, tmp_path):
        """Test that get_script_paths finds .mbro files recursively."""
        # Create test directory structure
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        
        # Create some .mbro files
        (test_dir / "script1.mbro").write_text("# Script 1")
        subdir = test_dir / "subdir"
        subdir.mkdir()
        (subdir / "script2.mbro").write_text("# Script 2")
        
        # Create non-.mbro file
        (test_dir / "notscript.py").write_text("# Not a script")
        
        # Test with custom MAGG_PATH
        with patch.dict(os.environ, {"MAGG_PATH": str(test_dir)}):
            config = MaggConfig()
            scripts = config.get_script_paths()
            
            # Should find both .mbro files
            script_names = [s.name for s in scripts]
            assert "script1.mbro" in script_names
            assert "script2.mbro" in script_names
            assert len(scripts) == 2
            
            # Should not include .py file
            assert "notscript.py" not in script_names

    def test_add_remove_server(self):
        """Test adding and removing servers."""
        config = MaggConfig()

        server = ServerConfig(name="test", source="https://example.com")  # prefix auto-generated
        config.add_server(server)

        assert "test" in config.servers
        assert config.servers["test"] == server

        # Remove server
        assert config.remove_server("test") is True
        assert "test" not in config.servers

        # Remove non-existent
        assert config.remove_server("nonexistent") is False

    def test_get_enabled_servers(self):
        """Test getting only enabled servers."""
        config = MaggConfig()

        server1 = ServerConfig(name="enabled1", source="test", enabled=True)  # prefix auto-generated
        server2 = ServerConfig(name="disabled", source="test", enabled=False)  # prefix auto-generated
        server3 = ServerConfig(name="enabled2", source="test", enabled=True)  # prefix auto-generated

        config.add_server(server1)
        config.add_server(server2)
        config.add_server(server3)

        enabled = config.get_enabled_servers()
        assert len(enabled) == 2
        assert "enabled1" in enabled
        assert "enabled2" in enabled
        assert "disabled" not in enabled


class TestConfigManager:
    """Test ConfigManager functionality."""

    def test_config_manager_initialization(self):
        """Test ConfigManager initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            manager = ConfigManager(str(config_path))

            assert manager.config_path == config_path
            assert config_path.parent.exists()

    def test_save_load_config(self):
        """Test saving and loading configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            manager = ConfigManager(str(config_path))

            # Create config with servers
            config = MaggConfig()
            server1 = ServerConfig(
                name="server1",
                source="https://example.com/1",
                command="python",
                args=["test.py"]
            )  # prefix auto-generated as "server1"
            server2 = ServerConfig(
                name="server2",
                source="https://example.com/2",
                uri="http://localhost:8080",
                enabled=False
            )  # prefix auto-generated as "server2"

            config.add_server(server1)
            config.add_server(server2)

            # Save config
            assert manager.save_config(config) is True
            assert config_path.exists()

            # Load config
            loaded_config = manager.load_config()
            assert len(loaded_config.servers) == 2
            assert "server1" in loaded_config.servers
            assert "server2" in loaded_config.servers

            # Check server details preserved
            loaded_server1 = loaded_config.servers["server1"]
            assert loaded_server1.name == "server1"
            assert loaded_server1.command == "python"
            assert loaded_server1.args == ["test.py"]
            assert loaded_server1.enabled is True

            loaded_server2 = loaded_config.servers["server2"]
            assert loaded_server2.uri == "http://localhost:8080"
            assert loaded_server2.enabled is False

    def test_load_nonexistent_config(self):
        """Test loading when config doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent.json"
            manager = ConfigManager(str(config_path))

            config = manager.load_config()
            assert config.servers == {}

    def test_load_invalid_config(self):
        """Test loading invalid config gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "invalid.json"

            # Write invalid JSON
            with open(config_path, 'w') as f:
                f.write("{invalid json")

            manager = ConfigManager(str(config_path))
            config = manager.load_config()

            # Should return empty config on error
            assert config.servers == {}
