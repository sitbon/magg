"""Integration tests for Magg server functionality."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from magg.server import MaggServer
from magg.settings import MaggConfig, ConfigManager, ServerConfig


class TestIntegration:
    """Test full integration of server creation and management."""

    @pytest.mark.asyncio
    async def test_add_python_server(self):
        """Test adding a local Python server."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test Python script
            server_script = Path(tmpdir) / "test_server.py"
            server_script.write_text('''
from fastmcp import FastMCP

mcp = FastMCP("test-python-server")

@mcp.tool()
def test_tool(message: str) -> str:
    return f"Test response: {message}"

if __name__ == "__main__":
    mcp.run()
''')

            # Create Magg server
            config_path = Path(tmpdir) / "config.json"
            server = MaggServer(str(config_path))

            # Add the server
            result = await server.add_server(
                name="pythontest",
                source="file://" + str(tmpdir),
                command=f"python {server_script}",
                working_dir=str(tmpdir)
            )

            assert result.is_success
            assert result.output["server"]["name"] == "pythontest"
            assert result.output["server"]["command"] == f"python {server_script}"

            # Verify it was saved
            config = server.config
            assert "pythontest" in config.servers

    @pytest.mark.asyncio
    async def test_add_server_with_python_module(self):
        """Test adding a Python server using -m module syntax."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Magg server
            config_path = Path(tmpdir) / "config.json"
            server = MaggServer(str(config_path))

            # Add server with -m syntax
            result = await server.add_server(
                name="moduletest",
                source="https://github.com/example/module-server",
                command="python -m example.server --port 8080",
                working_dir=str(tmpdir)
            )

            assert result.is_success
            assert result.output["server"]["command"] == "python -m example.server --port 8080"

    @pytest.mark.asyncio
    async def test_transport_selection(self):
        """Test that correct transport is selected based on command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            server = MaggServer(str(config_path))

            # Test Python transport
            result = await server.add_server(
                name="pythontransport",
                source="https://example.com",
                command="python script.py"
            )
            assert result.is_success

            # Test Node transport
            result = await server.add_server(
                name="nodetransport",
                source="https://example.com",
                command="node server.js"
            )
            assert result.is_success

            # Test NPX transport
            result = await server.add_server(
                name="npxtransport",
                source="https://example.com",
                command="npx @example/server"
            )
            assert result.is_success

            # Test UVX transport
            result = await server.add_server(
                name="uvxtransport",
                source="https://example.com",
                command="uvx example-server"
            )
            assert result.is_success

            # Test HTTP transport
            result = await server.add_server(
                name="httptransport",
                source="https://example.com",
                uri="http://localhost:8080"
            )
            assert result.is_success

            # Verify all were saved
            config = server.config
            assert len(config.servers) == 5


class TestServerLifecycle:
    """Test server lifecycle management."""

    @pytest.mark.asyncio
    async def test_enable_disable_server(self):
        """Test enabling and disabling servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            server = MaggServer(str(config_path))

            # Add a disabled server
            result = await server.add_server(
                name="lifecycle",
                source="https://example.com",
                command="echo test",
                enable=False
            )
            assert result.is_success
            assert result.output["server"]["enabled"] is False

            # Enable it
            result = await server.enable_server("lifecycle")
            assert result.is_success

            # Check it's enabled in config
            config = server.config
            assert config.servers["lifecycle"].enabled is True

            # Disable it again
            result = await server.disable_server("lifecycle")
            assert result.is_success

            # Check it's disabled
            config = server.config
            assert config.servers["lifecycle"].enabled is False

    @pytest.mark.asyncio
    async def test_remove_server(self):
        """Test removing servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            server = MaggServer(str(config_path))

            # Add a server
            await server.add_server(
                name="toremove",
                source="https://example.com",
                command="echo test"
            )

            # Remove it
            result = await server.remove_server("toremove")
            assert result.is_success

            # Verify it's gone
            config = server.config
            assert "toremove" not in config.servers

            # Try to remove non-existent
            result = await server.remove_server("nonexistent")
            assert result.is_error
