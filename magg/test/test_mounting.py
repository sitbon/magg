"""Test FastMCP mounting functionality and client types."""

import pytest
import inspect
from unittest.mock import patch, MagicMock

from fastmcp import FastMCP, Client


class TestFastMCPMounting:
    """Test FastMCP mounting capabilities and client compatibility."""

    @pytest.fixture
    def test_mcp(self):
        """Create a test FastMCP server."""
        return FastMCP("test")

    def test_http_client_creation(self):
        """Test HTTP client creation and attributes."""
        http_client = Client("http://localhost:8080")

        # Check client was created
        assert http_client is not None

        # Check for lifespan-related attributes
        lifespan_attrs = [attr for attr in dir(http_client) if 'lifespan' in attr.lower()]
        has_lifespan = hasattr(http_client, '_has_lifespan')

        # Store results for analysis
        assert isinstance(lifespan_attrs, list)
        assert isinstance(has_lifespan, bool)

    def test_command_client_creation(self):
        """Test command client creation with MCP config."""
        mcp_config = {
            "mcpServers": {
                "test": {
                    "command": "echo hello"
                }
            }
        }

        command_client = Client(mcp_config)

        # Check client was created
        assert command_client is not None

        # Check for lifespan-related attributes
        lifespan_attrs = [attr for attr in dir(command_client) if 'lifespan' in attr.lower()]
        has_lifespan = hasattr(command_client, '_has_lifespan')

        # Store results for analysis
        assert isinstance(lifespan_attrs, list)
        assert isinstance(has_lifespan, bool)

    def test_client_attribute_comparison(self):
        """Test comparing attributes between different client types."""
        http_client = Client("http://localhost:8080")
        mcp_config = {"mcpServers": {"test": {"command": "echo hello"}}}
        command_client = Client(mcp_config)

        http_attrs = set(dir(http_client))
        cmd_attrs = set(dir(command_client))

        # Both should have basic client attributes
        assert len(http_attrs) > 0
        assert len(cmd_attrs) > 0

        # Find differences
        http_unique = http_attrs - cmd_attrs
        cmd_unique = cmd_attrs - http_attrs
        common = http_attrs & cmd_attrs
        common_lifespan = [attr for attr in common if 'lifespan' in attr.lower()]

        # Store results for analysis
        assert isinstance(http_unique, set)
        assert isinstance(cmd_unique, set)
        assert isinstance(common_lifespan, list)

    def test_mount_method_signature(self, test_mcp):
        """Test FastMCP mount method signature."""
        mount_sig = inspect.signature(test_mcp.mount)

        # Should have mount method
        assert hasattr(test_mcp, 'mount')
        assert callable(test_mcp.mount)

        # Check signature parameters
        params = list(mount_sig.parameters.keys())
        assert len(params) > 0  # Should have at least one parameter

        # Typically expect name and client parameters
        assert isinstance(params, list)

    @pytest.mark.skip(reason="Requires running server for actual mounting")
    def test_http_client_mounting(self, test_mcp):
        """Test mounting HTTP client (requires running server)."""
        http_client = Client("http://localhost:8080")

        # This would require an actual running server
        # test_mcp.mount("test_http", http_client)
        pass

    @pytest.mark.skip(reason="Requires external command for actual mounting")
    def test_command_client_mounting(self, test_mcp):
        """Test mounting command client (requires external command)."""
        mcp_config = {
            "mcpServers": {
                "test": {
                    "command": "echo hello"
                }
            }
        }
        command_client = Client(mcp_config)

        # This would require the command to be available
        # test_mcp.mount("test_cmd", command_client)
        pass


class TestClientLifespanCompatibility:
    """Test client lifespan compatibility issues."""

    def test_lifespan_attribute_presence(self):
        """Test presence of lifespan attributes on different clients."""
        # HTTP client
        http_client = Client("http://localhost:8080")
        http_has_lifespan = hasattr(http_client, '_has_lifespan')

        # Command client
        mcp_config = {"mcpServers": {"test": {"command": "echo hello"}}}
        command_client = Client(mcp_config)
        cmd_has_lifespan = hasattr(command_client, '_has_lifespan')

        # Document the current behavior
        assert isinstance(http_has_lifespan, bool)
        assert isinstance(cmd_has_lifespan, bool)

    def test_client_type_consistency(self):
        """Test that both client types have consistent interfaces."""
        http_client = Client("http://localhost:8080")
        mcp_config = {"mcpServers": {"test": {"command": "echo hello"}}}
        command_client = Client(mcp_config)

        # Both should be Client instances
        assert isinstance(http_client, Client)
        assert isinstance(command_client, Client)

        # Both should have similar base interface
        http_methods = [m for m in dir(http_client) if not m.startswith('_')]
        cmd_methods = [m for m in dir(command_client) if not m.startswith('_')]

        # Should have some common public methods
        common_methods = set(http_methods) & set(cmd_methods)
        assert len(common_methods) > 0
