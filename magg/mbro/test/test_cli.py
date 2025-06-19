#!/usr/bin/env python3
"""Tests for mbro CLI functionality."""

import sys
import pytest
from unittest.mock import Mock, AsyncMock, patch
from magg.mbro.cli import MCPBrowserCLI


class TestMCPBrowserCLI:
    """Test mbro CLI functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.cli = MCPBrowserCLI(use_rich=False)  # Use plain print for testing
        self.cli.running = False  # Don't actually run the CLI
    
    @pytest.mark.asyncio
    async def test_handle_help_command(self):
        """Test help command."""
        with patch('builtins.print') as mock_print:
            await self.cli.handle_command("help")
            mock_print.assert_called()
            # Check that help text was printed
            call_args = mock_print.call_args_list
            help_text = ''.join(str(call.args[0]) for call in call_args)
            assert "Available commands:" in help_text
    
    @pytest.mark.asyncio
    async def test_handle_quit_command(self):
        """Test quit command."""
        self.cli.running = True
        await self.cli.handle_command("quit")
        assert not self.cli.running
        
        self.cli.running = True
        await self.cli.handle_command("exit")
        assert not self.cli.running
    
    @pytest.mark.asyncio
    async def test_handle_unknown_command(self):
        """Test unknown command handling."""
        with patch('builtins.print') as mock_print:
            await self.cli.handle_command("unknown_command")
            # format_error adds "Error: " prefix and sends to stderr
            mock_print.assert_called_with("Error: Unknown command: unknown_command. Type 'help' for available commands.", file=sys.stderr)
    
    @pytest.mark.asyncio
    async def test_cmd_connect(self):
        """Test connect command."""
        with patch.object(self.cli.browser, 'add_connection') as mock_connect:
            mock_connect.return_value = True
            
            # Mock the connection that should exist after successful add
            mock_connection = Mock()
            mock_connection.get_tools = AsyncMock(return_value=[])
            mock_connection.get_resources = AsyncMock(return_value=[])
            mock_connection.get_prompts = AsyncMock(return_value=[])
            self.cli.browser.connections = {"test": mock_connection}
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_connect(["test", "http://localhost:8080"])
                
                mock_connect.assert_called_once_with("test", "http://localhost:8080")
                # Check that success message was printed
                call_args = mock_print.call_args_list
                output_text = ''.join(str(call.args[0]) for call in call_args if call.args)
                assert "Connected to 'test'" in output_text
    
    @pytest.mark.asyncio
    async def test_cmd_connect_insufficient_args(self):
        """Test connect command with insufficient arguments."""
        with patch('builtins.print') as mock_print:
            await self.cli.cmd_connect(["test"])
            # format_error adds "Error: " prefix and sends to stderr
            mock_print.assert_called_with("Error: Usage: connect <name> <connection_string>", file=sys.stderr)
    
    @pytest.mark.asyncio
    async def test_cmd_connections_empty(self):
        """Test connections command with no connections."""
        with patch.object(self.cli.browser, 'list_connections') as mock_list:
            mock_list.return_value = []
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_connections()
                mock_print.assert_any_call("No connections configured.")
    
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
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_connections()
                
                # Check that connection info was printed
                call_args = mock_print.call_args_list
                output_text = ''.join(str(call.args[0]) for call in call_args)
                assert "test" in output_text
                assert "http" in output_text
                assert "current" in output_text
    
    @pytest.mark.asyncio
    async def test_cmd_tools_no_connection(self):
        """Test tools command with no active connection."""
        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = None
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_tools([])
                mock_print.assert_called_with("Error: No active connection.", file=sys.stderr)
    
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
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_tools([])
                
                # Check that tools were printed as JSON
                call_args = mock_print.call_args_list
                output_text = ''.join(str(call.args[0]) for call in call_args if call.args)
                assert "test_tool" in output_text
                assert "calc_add" in output_text
                # The formatter outputs JSON, not formatted text with "Arguments:"
                assert '"name": "calc_add"' in output_text
    
    @pytest.mark.asyncio
    async def test_cmd_tools_with_filter(self):
        """Test tools command with filter."""
        mock_connection = Mock()
        mock_connection.get_tools = AsyncMock(return_value=[
            {
                "name": "test_tool",
                "description": "A test tool"
            },
            {
                "name": "calc_add",
                "description": "Calculator addition"
            }
        ])
        
        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = mock_connection
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_tools(["calc"])
                
                # Should only show calc_add
                call_args = mock_print.call_args_list
                output_text = ''.join(str(call.args[0]) for call in call_args if call.args)
                assert "calc_add" in output_text
                assert "test_tool" not in output_text
    
    @pytest.mark.asyncio 
    async def test_cmd_call_tool(self):
        """Test calling a tool."""
        mock_connection = Mock()
        mock_result = [Mock()]
        mock_result[0].text = "Tool result"
        mock_connection.call_tool = AsyncMock(return_value=mock_result)
        
        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = mock_connection
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_call(["test_tool", '{"arg": "value"}'])
                
                mock_connection.call_tool.assert_called_once_with("test_tool", {"arg": "value"})
                
                # Check output
                call_args = mock_print.call_args_list
                output_text = ''.join(str(call.args[0]) for call in call_args if call.args)
                assert "Tool result" in output_text
    
    @pytest.mark.asyncio
    async def test_cmd_call_tool_invalid_json(self):
        """Test calling a tool with invalid JSON arguments."""
        mock_connection = Mock()
        
        with patch.object(self.cli.browser, 'get_current_connection') as mock_get:
            mock_get.return_value = mock_connection
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_call(["test_tool", "invalid json"])
                
                # Should show JSON error
                call_args = mock_print.call_args_list
                output_text = ''.join(str(call.args[0]) for call in call_args if call.args)
                assert "Invalid JSON" in output_text
    
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
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_search(["calc"])
                
                # Should find calc_add
                call_args = mock_print.call_args_list
                output_text = ''.join(str(call.args[0]) for call in call_args if call.args)
                assert "calc_add" in output_text
                assert "test_tool" not in output_text
    
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
            
            with patch('builtins.print') as mock_print:
                await self.cli.cmd_info(["tool", "test_tool"])
                
                # Should show detailed tool info as JSON
                call_args = mock_print.call_args_list
                output_text = ''.join(str(call.args[0]) for call in call_args if call.args)
                assert "test_tool" in output_text
                # The formatter outputs JSON, not formatted text with "Input Schema:"
                assert '"inputSchema"' in output_text


if __name__ == "__main__":
    pytest.main([__file__])