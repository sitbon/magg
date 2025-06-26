#!/usr/bin/env python3
"""Tests for mbro client functionality."""

import pytest
from magg.mbro.client import MCPConnection, MCPBrowser


class TestMCPConnection:
    """Test MCP connection functionality."""

    def test_init(self):
        """Test connection initialization."""
        conn = MCPConnection("test", "command", "echo hello")
        assert conn.name == "test"
        assert conn.connection_type == "command"
        assert conn.connection_string == "echo hello"
        assert not conn.connected
        # tools, resources, prompts are now async methods

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful connection."""
        # This would need a real MCP server to test properly
        # For now, just test the structure
        conn = MCPConnection("test", "command", "echo hello")
        # We can't easily test actual connection without a mock server
        assert conn.connected == False  # Should be False until we connect


class TestMCPBrowser:
    """Test MCP browser functionality."""

    def test_init(self):
        """Test browser initialization."""
        browser = MCPBrowser()
        assert browser.connections == {}
        assert browser.current_connection is None

    @pytest.mark.asyncio
    async def test_list_connections_empty(self):
        """Test listing connections when none exist."""
        browser = MCPBrowser()
        connections = await browser.list_connections()
        assert connections == []

    def test_get_current_connection_none(self):
        """Test getting current connection when none exists."""
        browser = MCPBrowser()
        current = browser.get_current_connection()
        assert current is None


if __name__ == "__main__":
    pytest.main([__file__])
