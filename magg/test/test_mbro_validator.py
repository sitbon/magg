"""Tests for mbro input validator."""

import pytest
from unittest.mock import MagicMock
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from magg.mbro.validator import InputValidator


class TestInputValidator:
    """Test the InputValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance with a mock CLI."""
        mock_cli = MagicMock()
        return InputValidator(mock_cli)

    def test_empty_input_valid(self, validator):
        """Test that empty input is valid."""
        doc = Document("")
        validator.validate(doc)  # Should not raise

    def test_complete_command_valid(self, validator):
        """Test that complete commands are valid."""
        # Simple commands
        for cmd in ["help", "quit", "tools", "resources"]:
            doc = Document(cmd)
            validator.validate(doc)  # Should not raise

        # Commands with arguments
        doc = Document("call my_tool")
        validator.validate(doc)  # Should not raise

    def test_backslash_continuation(self, validator):
        """Test that backslash at end of line needs continuation."""
        assert validator._needs_continuation("some command \\")
        assert not validator._needs_continuation("some command")

    def test_unclosed_quotes(self, validator):
        """Test detection of unclosed quotes."""
        assert validator._has_unclosed_quotes('hello "world')
        assert validator._has_unclosed_quotes("hello 'world")
        assert not validator._has_unclosed_quotes('hello "world"')
        assert not validator._has_unclosed_quotes("hello 'world'")
        
        # Test escaped quotes
        assert not validator._has_unclosed_quotes('hello "world\\"quote"')
        assert validator._has_unclosed_quotes('hello "world\\"')

    def test_unclosed_brackets(self, validator):
        """Test detection of unclosed brackets."""
        assert validator._has_unclosed_brackets("call tool {")
        assert validator._has_unclosed_brackets("call tool { 'key': [")
        assert not validator._has_unclosed_brackets("call tool {}")
        assert not validator._has_unclosed_brackets("call tool { 'key': [] }")
        
        # Test brackets in strings
        assert not validator._has_unclosed_brackets('call tool "{"')
        assert validator._has_unclosed_brackets('call tool "{" {')

    def test_syntax_errors(self, validator):
        """Test detection of syntax errors in key=value pairs."""
        # Valid key=value pairs
        assert not validator._has_syntax_errors("call tool key=value")
        assert not validator._has_syntax_errors("call tool key1=value1 key2=value2")
        
        # Invalid key=value pairs
        assert validator._has_syntax_errors("call tool =value")
        assert validator._has_syntax_errors("call tool key=")
        
        # JSON args shouldn't be checked for key=value syntax
        assert not validator._has_syntax_errors('call tool {"key": "value"}')

    def test_valid_pair(self, validator):
        """Test key=value pair validation."""
        assert validator._is_valid_pair("key=value")
        assert validator._is_valid_pair("key=123")
        assert not validator._is_valid_pair("=value")
        assert not validator._is_valid_pair("key=")
        assert not validator._is_valid_pair("invalid")

    def test_complete_mbro_command(self, validator):
        """Test detection of complete mbro commands."""
        # Standalone commands
        assert validator._is_complete_mbro_command("help")
        assert validator._is_complete_mbro_command("quit")
        assert validator._is_complete_mbro_command("tools")
        
        # Commands that need arguments
        assert not validator._is_complete_mbro_command("call")
        assert validator._is_complete_mbro_command("call my_tool")
        assert not validator._is_complete_mbro_command("connect")
        assert validator._is_complete_mbro_command("connect name stdio")
        
        # Unknown commands
        assert not validator._is_complete_mbro_command("unknown")
        assert not validator._is_complete_mbro_command("")