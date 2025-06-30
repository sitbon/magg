"""Tests for mbro CLI JSON parsing functionality."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from magg.mbro.cli import MCPBrowserCLI
import json


class TestJSONParsing:
    """Test JSON parsing in mbro CLI."""
    
    @pytest.fixture
    def cli(self):
        """Create a CLI instance for testing."""
        return MCPBrowserCLI(json_only=True)
    
    @pytest.mark.asyncio
    async def test_json_without_quotes(self, cli):
        """Test that JSON can be passed without quotes around the entire object."""
        mock_connection = Mock()
        mock_connection.get_tools = AsyncMock(return_value=[
            {"name": "test_echo", "inputSchema": {"type": "object"}}
        ])
        
        from mcp.types import TextContent
        expected_args = {"objekt": 123, "message": "hello"}
        mock_connection.call_tool = AsyncMock(
            return_value=[TextContent(type="text", text=json.dumps(expected_args))]
        )
        
        # Simulate the command processing
        command = 'call test_echo {"objekt": 123, "message": "hello"}'
        
        # Process like handle_command does
        command = command.replace('\\\n', ' ').replace('\n', ' ').strip()
        
        # Check special JSON handling
        json_start = command.find('{')
        prefix = command[:json_start].strip()
        json_part = command[json_start:].strip()
        
        assert json_part == '{"objekt": 123, "message": "hello"}'
        assert json.loads(json_part) == expected_args
        
        # Test through actual command handling
        with patch.object(cli.browser, 'get_current_connection', return_value=mock_connection):
            await cli.handle_command(command)
            
            # Verify the tool was called with correct arguments
            mock_connection.call_tool.assert_called_once_with("test_echo", expected_args)
    
    @pytest.mark.asyncio
    async def test_json_with_nested_objects(self, cli):
        """Test JSON with nested objects and arrays."""
        mock_connection = Mock()
        mock_connection.get_tools = AsyncMock(return_value=[
            {"name": "complex_tool", "inputSchema": {"type": "object"}}
        ])
        
        nested_json = {
            "user": {"name": "John", "age": 30},
            "items": [1, 2, 3],
            "enabled": True
        }
        
        from mcp.types import TextContent
        mock_connection.call_tool = AsyncMock(
            return_value=[TextContent(type="text", text="success")]
        )
        
        command = f'call complex_tool {json.dumps(nested_json)}'
        
        with patch.object(cli.browser, 'get_current_connection', return_value=mock_connection):
            await cli.handle_command(command)
            
            mock_connection.call_tool.assert_called_once_with("complex_tool", nested_json)
    
    @pytest.mark.asyncio
    async def test_shell_style_args_still_work(self, cli):
        """Test that shell-style key=value arguments still work."""
        mock_connection = Mock()
        mock_connection.get_tools = AsyncMock(return_value=[
            {"name": "test_tool", "inputSchema": {"type": "object"}}
        ])
        
        from mcp.types import TextContent
        mock_connection.call_tool = AsyncMock(
            return_value=[TextContent(type="text", text="success")]
        )
        
        with patch.object(cli.browser, 'get_current_connection', return_value=mock_connection):
            await cli.handle_command('call test_tool message="hello world" count=42 enabled=true')
            
            expected_args = {"message": "hello world", "count": 42, "enabled": True}
            mock_connection.call_tool.assert_called_once_with("test_tool", expected_args)
    
    @pytest.mark.asyncio
    async def test_json_with_spaces_in_strings(self, cli):
        """Test JSON with spaces in string values."""
        mock_connection = Mock()
        mock_connection.get_tools = AsyncMock(return_value=[
            {"name": "test_tool", "inputSchema": {"type": "object"}}
        ])
        
        from mcp.types import TextContent
        mock_connection.call_tool = AsyncMock(
            return_value=[TextContent(type="text", text="success")]
        )
        
        with patch.object(cli.browser, 'get_current_connection', return_value=mock_connection):
            await cli.handle_command('call test_tool {"message": "hello world", "path": "/home/user/my files/test.txt"}')
            
            expected_args = {"message": "hello world", "path": "/home/user/my files/test.txt"}
            mock_connection.call_tool.assert_called_once_with("test_tool", expected_args)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])