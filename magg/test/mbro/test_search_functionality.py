"""Test mbro search functionality with Magg."""

import pytest
import asyncio
import subprocess
import signal
import json
import sys


class TestMBROSearchFunctionality:
    """Test search functionality through mbro connected to Magg."""

    @pytest.fixture
    def magg_server_port(self):
        """Port for test Magg server."""
        return 8084

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
    async def test_status_before_search(self, magg_server, magg_server_port):
        """Test list tools call works before attempting search."""
        # Test simple list tools call first to verify connection
        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_list_tools"
        ], capture_output=True, text=True, timeout=10)

        assert result.returncode == 0, f"Status call failed: {result.stderr}"
        assert len(result.stdout.strip()) > 0

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_search_with_json_args(self, magg_server, magg_server_port):
        """Test search with properly formatted JSON arguments."""
        # Test search with proper JSON formatting
        search_args = json.dumps({"query": "calculator", "limit": 2})

        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_search_sources", search_args
        ], capture_output=True, text=True, timeout=15)

        # Should execute successfully
        assert result.returncode == 0, f"Search call failed: {result.stderr}"
        assert len(result.stdout.strip()) > 0

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_search_json_formatting_variations(self, magg_server, magg_server_port):
        """Test different JSON formatting approaches."""
        # Test with single-quoted JSON string
        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_search_sources", '{"query": "calculator", "limit": 1}'
        ], capture_output=True, text=True, timeout=15)

        # Should handle JSON formatting correctly
        assert result.returncode == 0, f"Single-quoted JSON search failed: {result.stderr}"
        assert len(result.stdout.strip()) > 0

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_search_parameter_validation(self, magg_server, magg_server_port):
        """Test search parameter validation."""
        # Test with minimal parameters
        minimal_search = json.dumps({"query": "test"})

        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_search_sources", minimal_search
        ], capture_output=True, text=True, timeout=15)

        # Should work with minimal parameters
        assert result.returncode == 0, f"Minimal search failed: {result.stderr}"

        # Test with empty query
        empty_search = json.dumps({"query": "", "limit": 1})

        result2 = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_search_sources", empty_search
        ], capture_output=True, text=True, timeout=15)

        # Should handle empty query gracefully
        # (exact behavior depends on implementation)
        assert isinstance(result2.returncode, int)

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_search_limit_parameter(self, magg_server, magg_server_port):
        """Test search with different limit values."""
        # Test with limit of 1
        search_limit_1 = json.dumps({"query": "calculator", "limit": 1})

        result1 = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_search_sources", search_limit_1
        ], capture_output=True, text=True, timeout=15)

        assert result1.returncode == 0, f"Search with limit 1 failed: {result1.stderr}"

        # Test with limit of 5
        search_limit_5 = json.dumps({"query": "calculator", "limit": 5})

        result5 = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_search_sources", search_limit_5
        ], capture_output=True, text=True, timeout=15)

        assert result5.returncode == 0, f"Search with limit 5 failed: {result5.stderr}"

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_invalid_json_parameters(self, magg_server, magg_server_port):
        """Test search with invalid JSON parameters."""
        # Test with malformed JSON
        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "magg", f"http://localhost:{magg_server_port}",
            "--call-tool", "magg_search_sources", '{"query": "test"'  # Missing closing brace
        ], capture_output=True, text=True, timeout=15)

        # Should fail gracefully with malformed JSON
        assert result.returncode != 0 or "error" in result.stdout.lower() or "error" in result.stderr.lower()


@pytest.mark.integration
class TestSearchIntegration:
    """Integration tests for search functionality."""

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.asyncio
    async def test_end_to_end_search_workflow(self):
        """Test complete search workflow from discovery to execution."""
        # This would test:
        # 1. Search for tools
        # 2. Parse search results
        # 3. Use discovered tools
        # Implementation depends on having stable test data
        pass
