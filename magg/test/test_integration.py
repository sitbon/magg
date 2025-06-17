"""Integration tests for MAGG server functionality."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from magg.server import MAGGServer
from magg.settings import MAGGConfig, ConfigManager, ServerConfig


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
            
            # Create MAGG server
            config_path = Path(tmpdir) / "config.json"
            server = MAGGServer(str(config_path))
            
            # Add the server
            result = await server.add_server(
                name="pythontest",
                url="file://" + str(tmpdir),
                command="python",
                args=[str(server_script)],
                working_dir=str(tmpdir)
            )
            
            assert result.is_success
            assert result.output["server"]["name"] == "pythontest"
            assert result.output["server"]["command"] == "python"
            
            # Verify it was saved
            config = server.config_manager.load_config()
            assert "pythontest" in config.servers
    
    @pytest.mark.asyncio
    async def test_add_server_with_python_module(self):
        """Test adding a Python server using -m module syntax."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create MAGG server
            config_path = Path(tmpdir) / "config.json"
            server = MAGGServer(str(config_path))
            
            # Add server with -m syntax
            result = await server.add_server(
                name="moduletest",
                url="https://github.com/example/module-server",
                command="python",
                args=["-m", "example.server", "--port", "8080"],
                working_dir=str(tmpdir)
            )
            
            assert result.is_success
            assert result.output["server"]["args"] == ["-m", "example.server", "--port", "8080"]
    
    @pytest.mark.asyncio
    async def test_transport_selection(self):
        """Test that correct transport is selected based on command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            server = MAGGServer(str(config_path))
            
            # Test Python transport
            result = await server.add_server(
                name="pythontransport",
                url="https://example.com",
                command="python",
                args=["script.py"]
            )
            assert result.is_success
            
            # Test Node transport
            result = await server.add_server(
                name="nodetransport",
                url="https://example.com",
                command="node",
                args=["server.js"]
            )
            assert result.is_success
            
            # Test NPX transport
            result = await server.add_server(
                name="npxtransport",
                url="https://example.com",
                command="npx",
                args=["@example/server"]
            )
            assert result.is_success
            
            # Test UVX transport
            result = await server.add_server(
                name="uvxtransport",
                url="https://example.com",
                command="uvx",
                args=["example-server"]
            )
            assert result.is_success
            
            # Test HTTP transport
            result = await server.add_server(
                name="httptransport",
                url="https://example.com",
                uri="http://localhost:8080"
            )
            assert result.is_success
            
            # Verify all were saved
            config = server.config_manager.load_config()
            assert len(config.servers) == 5


class TestServerLifecycle:
    """Test server lifecycle management."""
    
    @pytest.mark.asyncio
    async def test_enable_disable_server(self):
        """Test enabling and disabling servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            server = MAGGServer(str(config_path))
            
            # Add a disabled server
            result = await server.add_server(
                name="lifecycle",
                url="https://example.com",
                command="echo",
                args=["test"],
                enable=False
            )
            assert result.is_success
            assert result.output["server"]["enabled"] is False
            
            # Enable it
            result = await server.enable_server("lifecycle")
            assert result.is_success
            
            # Check it's enabled in config
            config = server.config_manager.load_config()
            assert config.servers["lifecycle"].enabled is True
            
            # Disable it again
            result = await server.disable_server("lifecycle")
            assert result.is_success
            
            # Check it's disabled
            config = server.config_manager.load_config()
            assert config.servers["lifecycle"].enabled is False
    
    @pytest.mark.asyncio
    async def test_remove_server(self):
        """Test removing servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            server = MAGGServer(str(config_path))
            
            # Add a server
            await server.add_server(
                name="toremove",
                url="https://example.com",
                command="echo",
                args=["test"]
            )
            
            # Remove it
            result = await server.remove_server("toremove")
            assert result.is_success
            
            # Verify it's gone
            config = server.config_manager.load_config()
            assert "toremove" not in config.servers
            
            # Try to remove non-existent
            result = await server.remove_server("nonexistent")
            assert result.is_error