"""Test mbro tool calling functionality with Magg."""

import pytest
import asyncio
import subprocess
import signal
import json
import sys
from unittest.mock import patch, MagicMock


class TestMBROToolCalling:
    """Test calling tools through mbro connected to Magg."""

    @pytest.fixture
    def magg_server_port(self):
        """Port for test Magg server."""
        return 8082

    @pytest.fixture
    async def magg_server(self, magg_server_port):
        """Start a Magg HTTP server for testing."""
        # Start Magg HTTP server in background
        process = subprocess.Popen(
            ["uv", "run", "magg", "--http", "--port", str(magg_server_port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=None if sys.platform == "win32" else lambda: None
        )

        # Wait for server to start
        await asyncio.sleep(3)

        yield process

        # Cleanup
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_magg_list_tools_call(self, magg_server, magg_server_port):
        """Test calling Magg list tools through mbro."""
        # Test calling Magg list tools
        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_list_tools"
        ], capture_output=True, text=True, timeout=10)

        # Should execute successfully
        assert result.returncode == 0, f"Status call failed: {result.stderr}"

        # Should return some status information
        assert len(result.stdout.strip()) > 0

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_magg_search_sources(self, magg_server, magg_server_port):
        """Test searching for sources through mbro."""
        # Test source search with JSON parameters
        search_params = json.dumps({"query": "calculator", "limit": 2})

        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_search_sources", search_params
        ], capture_output=True, text=True, timeout=15)

        # Should execute successfully
        assert result.returncode == 0, f"Search call failed: {result.stderr}"

        # Should return search results
        assert len(result.stdout.strip()) > 0

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_magg_list_servers(self, magg_server, magg_server_port):
        """Test listing servers through mbro."""
        # Test listing servers
        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_list_servers"
        ], capture_output=True, text=True, timeout=10)

        # Should execute successfully
        assert result.returncode == 0, f"List servers call failed: {result.stderr}"

        # Should return server list information
        assert len(result.stdout.strip()) > 0

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_invalid_tool_call(self, magg_server, magg_server_port):
        """Test calling non-existent tool returns appropriate error."""
        # Test calling non-existent tool
        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "nonexistent_tool"
        ], capture_output=True, text=True, timeout=10)

        # Should fail gracefully
        assert result.returncode != 0
        assert len(result.stderr.strip()) > 0 or "error" in result.stdout.lower()


@pytest.mark.integration
class TestMBROToolIntegration:
    """Integration tests for mbro tool calling with actual Magg tools."""

    @pytest.mark.asyncio
    async def test_tool_discovery_workflow(self):
        """Test complete workflow of discovering and calling tools."""
        # This would test the full workflow:
        # 1. Connect to Magg
        # 2. List available tools
        # 3. Search for specific tools
        # 4. Call discovered tools
        # Implementation depends on having stable test environment
        pass

    @pytest.mark.asyncio
    async def test_tool_parameter_validation(self):
        """Test tool parameter validation through mbro."""
        # This would test calling tools with various parameter combinations
        # to ensure proper validation and error handling
        pass
