"""Test the new status and check tools."""

import pytest
from fastmcp import Client

from magg.server.server import MaggServer


class TestStatusAndCheckTools:
    """Test the status and check tools."""

    @pytest.mark.asyncio
    async def test_status_tool(self, tmp_path):
        """Test the magg_status tool returns proper statistics."""
        config_path = tmp_path / "config.json"
        server = MaggServer(config_path)
        await server.setup()

        async with Client(server.mcp) as client:
            result = await client.call_tool("magg_status", {})
            assert len(result) > 0

            # Parse the JSON response
            import json
            response = json.loads(result[0].text)

            # Extract the output from MaggResponse
            assert "output" in response
            data = response["output"]

            # Check the structure
            assert "servers" in data
            assert "tools" in data
            assert "prefixes" in data

            # Check server stats
            assert "total" in data["servers"]
            assert "enabled" in data["servers"]
            assert "mounted" in data["servers"]
            assert "disabled" in data["servers"]

            # Check tool stats
            assert "total" in data["tools"]

            assert data["servers"]["total"] == 0
            assert data["tools"]["total"] == 11  # Magg tools + proxy

    @pytest.mark.asyncio
    async def test_check_tool_report_mode(self, tmp_path):
        """Test the magg_check tool in report mode."""
        config_path = tmp_path / "config.json"
        server = MaggServer(config_path)
        await server.setup()

        async with Client(server.mcp) as client:
            # Test with no servers - should work
            result = await client.call_tool("magg_check", {"action": "report"})
            assert len(result) > 0

            # Parse the JSON response
            import json
            response = json.loads(result[0].text)

            # Extract the output from MaggResponse
            assert "output" in response
            data = response["output"]

            # Check the structure
            assert "servers_checked" in data
            assert "healthy" in data
            assert "unresponsive" in data
            assert "results" in data

            # With no servers
            assert data["servers_checked"] == 0
            assert data["healthy"] == 0
            assert data["unresponsive"] == 0

    @pytest.mark.asyncio
    async def test_check_tool_with_timeout(self, tmp_path):
        """Test the magg_check tool with custom timeout."""
        config_path = tmp_path / "config.json"
        server = MaggServer(config_path)
        await server.setup()

        async with Client(server.mcp) as client:
            # Test with custom timeout
            result = await client.call_tool("magg_check", {
                "action": "report",
                "timeout": 2.0
            })
            assert len(result) > 0

            # Should still work with no servers
            import json
            response = json.loads(result[0].text)
            data = response["output"]
            assert data["servers_checked"] == 0
