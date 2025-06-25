#!/usr/bin/env python3
"""Integration tests for mbro with real MCP servers."""

import asyncio
import subprocess
import time
import signal
import pytest
from pathlib import Path


class TestMbroIntegration:
    """Integration tests for mbro with real servers."""

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_http_connection_to_magg(self):
        """Test connecting to a real Magg HTTP server."""
        # Start Magg server
        magg_process = subprocess.Popen(
            ["uv", "run", "magg", "--http", "--port", "8090"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
        )

        try:
            # Wait for server to start
            await asyncio.sleep(3)

            # Test connection
            result = subprocess.run([
                "uv", "run", "mbro",
                "--connect", "magg_test", "http://localhost:8090",
                "--list-tools"
            ], capture_output=True, text=True, timeout=10)

            # Should successfully connect and list tools
            assert result.returncode == 0
            assert "Connected to 'magg_test'" in result.stdout
            assert "Tools (" in result.stdout
            assert "magg_list_tools" in result.stdout

        finally:
            # Clean up
            magg_process.terminate()
            try:
                magg_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                magg_process.kill()

    @pytest.mark.skip(reason="Complex integration test - needs external server")
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_tool_calling(self):
        """Test calling tools through mbro."""
        # Start Magg server
        magg_process = subprocess.Popen(
            ["uv", "run", "magg", "--http", "--port", "8091"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
        )

        try:
            # Wait for server to start
            await asyncio.sleep(3)

            # Test tool call
            result = subprocess.run([
                "uv", "run", "mbro",
                "--connect", "magg_test", "http://localhost:8091",
                "--call-tool", "magg_list_tools"
            ], capture_output=True, text=True, timeout=15)

            # Should successfully call tool
            assert result.returncode == 0
            assert "Connected to 'magg_test'" in result.stdout
            assert "Magg Status" in result.stdout
            assert "Configuration:" in result.stdout

        finally:
            # Clean up
            magg_process.terminate()
            try:
                magg_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                magg_process.kill()

    @pytest.mark.integration
    def test_invalid_connection(self):
        """Test connecting to invalid server."""
        result = subprocess.run([
            "uv", "run", "mbro",
            "--connect", "invalid", "http://localhost:9999",
            "--list-tools"
        ], capture_output=True, text=True, timeout=10)

        # Should fail to connect
        assert result.returncode == 1
        # The current implementation exits silently on connection failure
        # Just verify it exited with error code 1

    def test_cli_help(self):
        """Test CLI help output."""
        result = subprocess.run([
            "uv", "run", "mbro", "--help"
        ], capture_output=True, text=True, timeout=5)

        assert result.returncode == 0
        assert "MBRO - MCP Browser" in result.stdout
        assert "--connect" in result.stdout
        assert "--list-tools" in result.stdout

    def test_no_connection_error(self):
        """Test commands without connection."""
        result = subprocess.run([
            "uv", "run", "mbro", "--list-tools"
        ], capture_output=True, text=True, timeout=5)

        # Should show no connection error
        assert "No active connection" in result.stdout


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-m", "integration"])
