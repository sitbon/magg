"""Test error handling for invalid servers and edge cases."""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from magg.settings import ConfigManager, ServerConfig, MaggConfig
from magg.server import MaggServer


class TestErrorHandling:
    """Test error handling for various failure scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_server_connection(self):
        """Test handling of invalid server connections."""
        # Create a server config with invalid command
        invalid_server = ServerConfig(
            name="invalidserver",
            source="https://example.com/invalid",
            prefix="invalid",
            command="nonexistent-command",
            args=["--invalid-args"]
        )

        # Test that the invalid server is created but will fail on mount
        assert invalid_server.command == "nonexistent-command"
        assert invalid_server.args == ["--invalid-args"]

    @pytest.mark.asyncio
    async def test_malformed_config_handling(self):
        """Test handling of malformed configuration files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "malformed.json"

            # Write malformed JSON
            with open(config_path, 'w') as f:
                f.write('{"servers": {invalid json}')

            # ConfigManager should handle this gracefully
            manager = ConfigManager(str(config_path))
            config = manager.load_config()

            # Should return empty config on parse error
            assert config.servers == {}

    @pytest.mark.asyncio
    async def test_missing_command_handling(self):
        """Test server without command or URI."""
        # This should be valid - server can be created without command/URI
        server = ServerConfig(
            name="nocommand",
            source="https://example.com/test"
        )

        assert server.command is None
        assert server.uri is None

    @pytest.mark.asyncio
    async def test_duplicate_server_names(self):
        """Test handling of duplicate server names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            server = MaggServer(str(config_path))

            # Add first server
            result1 = await server.add_server(
                name="duplicate",
                source="https://example.com/1",
                command="echo test1"
            )
            assert result1.is_success

            # Try to add duplicate
            result2 = await server.add_server(
                name="duplicate",
                source="https://example.com/2",
                command="echo test2"
            )
            assert result2.is_error
            assert "already exists" in result2.errors[0]

    @pytest.mark.asyncio
    async def test_circular_dependency_handling(self):
        """Test handling of circular dependencies."""
        # In the new architecture, we don't have dependencies between servers
        # This test is no longer applicable
        pytest.skip("Circular dependencies not applicable in new architecture")

    @pytest.mark.asyncio
    async def test_invalid_url_format_handling(self):
        """Test handling of invalid URL formats."""
        # URLs are just strings, no validation enforced
        server = ServerConfig(
            name="test",
            source="not-a-valid-url"
        )
        assert server.source == "not-a-valid-url"

    @pytest.mark.asyncio
    async def test_environment_variable_handling(self):
        """Test handling of environment variables in server configs."""
        server = ServerConfig(
            name="envtest",
            source="https://example.com",
            env={"TEST_VAR": "value", "ANOTHER_VAR": "another"}
        )

        assert server.env == {"TEST_VAR": "value", "ANOTHER_VAR": "another"}


class TestConfigValidation:
    """Test configuration validation and error cases."""

    def test_empty_config_creation(self):
        """Test creating empty configuration."""
        config = MaggConfig()
        assert config.servers == {}
        assert len(config.get_enabled_servers()) == 0

    def test_server_without_url(self):
        """Test that server requires URL."""
        with pytest.raises(Exception):  # Pydantic will raise validation error
            ServerConfig(name="test")  # Missing required 'url' field

    def test_server_without_required_fields(self):
        """Test server with minimal required fields."""
        # Only name and url are required
        server = ServerConfig(
            name="minimal",
            source="https://example.com"
        )

        assert server.name == "minimal"
        assert server.source == "https://example.com"
        assert server.command is None
        assert server.args is None


class TestMountingErrors:
    """Test error handling during server mounting."""

    @pytest.mark.asyncio
    async def test_mount_nonexistent_command(self):
        """Test mounting server with non-existent command."""
        server = MaggServer()

        with patch.object(server.server_manager, 'mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = False  # Simulate mount failure

            result = await server.add_server(
                name="badcommand",
                source="https://example.com",
                command="this-command-does-not-exist --help"
            )

            assert result.is_error
            assert "Failed to mount" in result.errors[0]

    @pytest.mark.asyncio
    async def test_mount_with_invalid_working_dir(self):
        """Test mounting server with invalid working directory."""
        server = MaggServer()

        with patch('magg.server.server.validate_working_directory') as mock_validate:
            mock_validate.return_value = (None, "Invalid working directory")

            result = await server.add_server(
                name="badworkdir",
                source="https://example.com",
                command="python test.py",
                working_dir="/nonexistent/directory"
            )

            assert result.is_error
            assert "Invalid working directory" in result.errors[0]
