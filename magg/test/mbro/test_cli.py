#!/usr/bin/env python3
"""Tests for mbro CLI functionality."""

import io
import json
import sys
from contextlib import redirect_stdout

import pytest
from unittest.mock import Mock, AsyncMock, patch
from magg.mbro.cli import MCPBrowserCLI


class TestMCPBrowserCLI:
    """Test mbro CLI functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cli = MCPBrowserCLI(json_only=True, use_rich=False)  # Use JSON output for testing
        self.cli.running = False  # Don't actually run the CLI

    async def capture_json_output(self, coro):
        """Helper to capture JSON output from async CLI commands."""
        f = io.StringIO()
        with redirect_stdout(f):
            await coro
        output = f.getvalue().strip()

        # Try to parse as JSON
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            # If not valid JSON, return the raw output
            return output

    @pytest.mark.asyncio
    async def test_handle_help_command(self):
        """Test help command."""
        output = await self.capture_json_output(self.cli.handle_command("help"))

        # Check that help was returned as JSON
        assert isinstance(output, dict)
        assert "help" in output
        assert "connection_management" in output["help"]
        assert "server_exploration" in output["help"]
        assert "tool_interaction" in output["help"]

    @pytest.mark.asyncio
    async def test_handle_quit_command(self):
        """Test quit command."""
        self.cli.running = True
        await self.cli.handle_command("quit")
        assert not self.cli.running

    @pytest.mark.asyncio
    async def test_handle_unknown_command(self):
        """Test unknown command handling."""
        output = await self.capture_json_output(self.cli.handle_command("foobar"))

        # Should show error as JSON
        assert isinstance(output, dict)
        assert "error" in output
        assert "Unknown command" in output["error"]

    @pytest.mark.asyncio
    async def test_cmd_connect(self):
        """Test connect command."""
        with patch.object(self.cli.browser, 'add_connection') as mock_add:
            mock_add.return_value = True

            # Create a mock connection
            mock_connection = Mock()
            mock_connection.get_tools = AsyncMock(return_value=[])
            mock_connection.get_resources = AsyncMock(return_value=[])
            mock_connection.get_prompts = AsyncMock(return_value=[])

            with patch.object(self.cli.browser, 'connections', {"test": mock_connection}):
                output = await self.capture_json_output(
                    self.cli.cmd_connect(["test", "http://localhost:8080"])
                )

                mock_add.assert_called_once_with("test", "http://localhost:8080")
                # Success message as JSON
                assert isinstance(output, dict)
                assert "success" in output
                assert "Connected to 'test'" in output["success"]

    @pytest.mark.asyncio
    async def test_cmd_connect_insufficient_args(self):
        """Test connect command with insufficient arguments."""
        output = await self.capture_json_output(self.cli.cmd_connect(["test"]))

        # Should show error as JSON
        assert isinstance(output, dict)
        assert "error" in output
        assert "Usage:" in output["error"]

    @pytest.mark.asyncio
    async def test_cmd_connections_empty(self):
        """Test connections command with no connections."""
        with patch.object(self.cli.browser, 'list_connections') as mock_list:
            mock_list.return_value = []

            output = await self.capture_json_output(self.cli.cmd_connections([]))

            # Should show info message as JSON
            assert isinstance(output, dict)
            assert "info" in output
            assert "No connections configured." in output["info"]

    @pytest.mark.asyncio
    async def test_cmd_connections_with_data(self):
        """Test connections command with connection data."""
        mock_connections = [
            {
                "name": "test",
                "type": "http",
                "connected": True,
                "current": True,
                "tools": 5,
                "resources": 2,
                "prompts": 1
            }
        ]

        with patch.object(self.cli.browser, 'list_connections') as mock_list:
            mock_list.return_value = mock_connections

            output = await self.capture_json_output(self.cli.cmd_connections([]))

            # Should show connections as JSON
            assert isinstance(output, dict)
            assert "connections" in output
            assert len(output["connections"]) == 1
            assert output["connections"][0]["name"] == "test"
            assert output["connections"][0]["current"] is True

    @pytest.mark.asyncio
    async def test_cmd_tools_no_connection(self):
        """Test tools command with no active connection."""
        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = None

            output = await self.capture_json_output(self.cli.cmd_tools([]))

            # Should show error as JSON
            assert isinstance(output, dict)
            assert "error" in output
            assert "No active connection" in output["error"]

    @pytest.mark.asyncio
    async def test_cmd_tools_with_data(self):
        """Test tools command with tool data."""
        mock_connection = Mock()
        mock_connection.get_tools = AsyncMock(return_value=[
            {
                "name": "test_tool",
                "description": "A test tool for testing"
            },
            {
                "name": "calc_add",
                "description": "Add two numbers\n\nArgs:\n    a: First number\n    b: Second number"
            }
        ])

        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = mock_connection

            output = await self.capture_json_output(self.cli.cmd_tools([]))

            # Should show tools as JSON
            assert isinstance(output, dict)
            assert "tools" in output
            assert len(output["tools"]) == 2
            assert output["tools"][0]["name"] == "test_tool"
            assert output["tools"][1]["name"] == "calc_add"

    @pytest.mark.asyncio
    async def test_cmd_tools_with_filter(self):
        """Test tools command with filter."""
        mock_connection = Mock()
        mock_connection.get_tools = AsyncMock(return_value=[
            {"name": "calc_add", "description": "Add numbers"},
            {"name": "calc_subtract", "description": "Subtract numbers"},
            {"name": "test_tool", "description": "Test functionality"}
        ])

        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = mock_connection

            output = await self.capture_json_output(self.cli.cmd_tools(["calc"]))

            # Should only show calc tools
            assert isinstance(output, dict)
            assert "tools" in output
            assert len(output["tools"]) == 2
            assert all("calc" in tool["name"] for tool in output["tools"])

    @pytest.mark.asyncio
    async def test_cmd_call_tool(self):
        """Test calling a tool."""
        mock_connection = Mock()

        # Mock tool result - the new format expects a Content object with type and text
        from mcp.types import TextContent
        mock_result = TextContent(type="text", text='{"result": "Tool result"}')
        mock_connection.call_tool = AsyncMock(return_value=[mock_result])

        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = mock_connection

            output = await self.capture_json_output(
                self.cli.cmd_call(["test_tool", '{"arg": "value"}'])
            )

            mock_connection.call_tool.assert_called_once_with("test_tool", {"arg": "value"})

            # Check output - JSON mode outputs a list of content objects
            assert isinstance(output, list)
            assert len(output) == 1
            # The formatter preserves the Content object structure since text is not JSON content type
            assert output[0]["type"] == "text"
            assert output[0]["text"] == '{"result": "Tool result"}'
            # Parse the text manually to verify
            import json
            parsed = json.loads(output[0]["text"])
            assert parsed["result"] == "Tool result"

    @pytest.mark.asyncio
    async def test_cmd_call_tool_invalid_json(self):
        """Test calling a tool with invalid JSON arguments."""
        mock_connection = Mock()

        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = mock_connection

            output = await self.capture_json_output(
                self.cli.cmd_call(["test_tool", "invalid json"])
            )

            # Should show error as JSON
            assert isinstance(output, dict)
            assert "error" in output
            assert "Invalid JSON" in output["error"]

    @pytest.mark.asyncio
    async def test_cmd_search(self):
        """Test search command."""
        mock_connection = Mock()
        mock_connection.get_tools = AsyncMock(return_value=[
            {"name": "calc_add", "description": "Add numbers"},
            {"name": "test_tool", "description": "Test functionality"}
        ])
        mock_connection.get_resources = AsyncMock(return_value=[])
        mock_connection.get_prompts = AsyncMock(return_value=[])

        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = mock_connection

            output = await self.capture_json_output(self.cli.cmd_search(["calc"]))

            # Should find calc_add in JSON output
            assert isinstance(output, dict)
            assert output["query"] == "calc"
            assert output["total_matches"] == 1
            assert len(output["tools"]) == 1
            assert output["tools"][0]["name"] == "calc_add"

    @pytest.mark.asyncio
    async def test_cmd_info_tool(self):
        """Test info command for tools."""
        mock_connection = Mock()
        mock_connection.get_tools = AsyncMock(return_value=[
            {
                "name": "test_tool",
                "description": "A test tool",
                "inputSchema": {"type": "object", "properties": {"arg": {"type": "string"}}}
            }
        ])

        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = mock_connection

            # Capture JSON output
            output = await self.capture_json_output(self.cli.cmd_info(["tool", "test_tool"]))

            # Verify JSON structure
            assert isinstance(output, dict)
            assert output["type"] == "tool"
            assert output["name"] == "test_tool"
            assert output["description"] == "A test tool"
            assert "inputSchema" in output


if __name__ == "__main__":
    pytest.main([__file__])
