"""Tests for the mbro CLI overhaul features."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from magg.mbro.cli import MCPBrowserCLI, handle_commands
from magg.mbro.parser import CommandParser


class TestCommandParser:
    """Test the new command parser functionality."""
    
    def test_parse_command_with_comments(self):
        """Test parsing commands with comments."""
        # Comment at end of line
        parts = CommandParser.parse_command_line("connect test python server.py # this is a comment")
        assert parts == ["connect", "test", "python", "server.py"]
        
        # Comment as whole line
        parts = CommandParser.parse_command_line("# just a comment")
        assert parts == []
        
        # Comment inside quotes should be preserved
        parts = CommandParser.parse_command_line('echo "hello # world"')
        assert parts == ["echo", "hello # world"]
    
    def test_split_commands_by_semicolon(self):
        """Test splitting multiple commands by semicolon."""
        commands = CommandParser.split_commands("connect test python server.py; tools")
        assert commands == ["connect test python server.py", "tools"]
        
        # With newlines
        commands = CommandParser.split_commands("connect test python server.py\ntools")
        assert commands == ["connect test python server.py", "tools"]
        
        # With line continuation
        commands = CommandParser.split_commands("connect test \\\npython server.py")
        assert commands == ["connect test python server.py"]
    
    def test_parse_connect_args(self):
        """Test parsing connect arguments: name and connection string."""
        # Basic usage: name followed by connection string
        name, conn = CommandParser.parse_connect_args(["myserver", "python", "server.py"])
        assert name == "myserver"
        assert conn == "python server.py"
        
        # Single word connection
        name, conn = CommandParser.parse_connect_args(["calc", "npx", "@playwright/mcp@latest"])
        assert name == "calc"
        assert conn == "npx @playwright/mcp@latest"
        
        # URL connection
        name, conn = CommandParser.parse_connect_args(["webserver", "http://localhost:8000/mcp"])
        assert name == "webserver"
        assert conn == "http://localhost:8000/mcp"
        
        # Should fail with insufficient args
        try:
            CommandParser.parse_connect_args(["python"])
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Usage: connect <name> <connection_string>" in str(e)
        
        # Should fail with no args
        try:
            CommandParser.parse_connect_args([])
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Usage: connect <name> <connection_string>" in str(e)


class TestMBroCLIOverhaul:
    """Test the mbro CLI overhaul features."""
    
    @pytest.mark.asyncio
    async def test_handle_commands_from_args(self):
        """Test handling commands from command line args."""
        cli = MagicMock()
        cli.handle_command = AsyncMock()
        
        args = MagicMock()
        args.commands = ["connect test python server.py", ";", "tools"]
        
        executed = await handle_commands(cli, args)
        
        assert executed is True
        assert cli.handle_command.call_count == 2
        cli.handle_command.assert_any_call("connect test python server.py")
        cli.handle_command.assert_any_call("tools")
    
    @pytest.mark.asyncio
    async def test_handle_commands_from_stdin(self):
        """Test handling commands from stdin."""
        cli = MagicMock()
        cli.handle_command = AsyncMock()
        
        args = MagicMock()
        args.commands = ["-"]
        
        # Mock stdin
        test_input = "connect test python server.py\ntools\n"
        with patch('sys.stdin.read', return_value=test_input):
            executed = await handle_commands(cli, args)
        
        assert executed is True
        assert cli.handle_command.call_count == 2
        cli.handle_command.assert_any_call("connect test python server.py")
        cli.handle_command.assert_any_call("tools")
    
    def test_cli_command_parsing_with_comments(self):
        """Test that CLI properly handles comments."""
        cli = MCPBrowserCLI(json_only=True)
        
        # Parse a command with a comment
        parts = CommandParser.parse_command_line("connect test python server.py # comment")
        assert parts == ["connect", "test", "python", "server.py"]