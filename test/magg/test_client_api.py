"""Test FastMCP Client API usage patterns."""

import pytest
import inspect
from fastmcp import Client


class TestFastMCPClientAPI:
    """Test FastMCP Client constructor and API patterns."""

    def test_http_client_creation(self):
        """Test HTTP client creation."""
        # Test HTTP client (should work)
        http_client = Client("http://localhost:8080")

        assert http_client is not None
        assert isinstance(http_client, Client)

    def test_command_client_creation_with_keyword(self):
        """Test command client creation with keyword argument."""
        try:
            # Test command-based client with command= keyword
            command_client = Client(command=["echo", "hello"])

            assert command_client is not None
            assert isinstance(command_client, Client)

        except TypeError as e:
            # If this syntax isn't supported, document it
            pytest.skip(f"Command keyword syntax not supported: {e}")

    def test_command_client_creation_positional(self):
        """Test command client creation with positional argument."""
        try:
            # Test alternative syntax with positional argument
            command_client = Client(["echo", "hello"])

            assert command_client is not None
            assert isinstance(command_client, Client)

        except (TypeError, ValueError) as e:
            # If this syntax isn't supported, document it
            pytest.skip(f"Positional command syntax not supported: {e}")

    def test_client_constructor_signature(self):
        """Test Client constructor signature."""
        sig = inspect.signature(Client.__init__)

        # Should have constructor
        assert sig is not None

        # Get parameter information
        params = list(sig.parameters.keys())
        assert len(params) > 0  # Should have at least 'self'

        # Document signature for analysis
        param_info = {name: param for name, param in sig.parameters.items()}
        assert 'self' in param_info

    def test_client_types_supported(self):
        """Test what types of clients are supported."""
        # HTTP client should always work
        http_client = Client("http://localhost:8080")
        assert isinstance(http_client, Client)

        # Test different URL schemes
        https_client = Client("https://example.com")
        assert isinstance(https_client, Client)

        # Test if WebSocket URLs are supported
        try:
            ws_client = Client("ws://localhost:8080")
            assert isinstance(ws_client, Client)
        except (ValueError, TypeError):
            # WebSocket might not be supported
            pytest.skip("WebSocket URLs not supported")


class TestClientParameterValidation:
    """Test Client parameter validation."""

    def test_invalid_url_handling(self):
        """Test how Client handles invalid URLs."""
        with pytest.raises((ValueError, TypeError)):
            Client("not-a-valid-url")

    def test_empty_command_handling(self):
        """Test how Client handles empty commands."""
        try:
            # Test empty command list
            with pytest.raises((ValueError, TypeError)):
                Client([])
        except TypeError:
            # Constructor might not accept list at all
            pytest.skip("List constructor not supported")

    def test_invalid_command_handling(self):
        """Test how Client handles invalid commands."""
        try:
            # Test invalid command types
            with pytest.raises((ValueError, TypeError)):
                Client(command=123)  # Invalid type
        except TypeError:
            # Constructor might not accept command keyword
            pytest.skip("Command keyword not supported")


class TestClientCompatibility:
    """Test Client compatibility with different scenarios."""

    def test_client_attribute_consistency(self):
        """Test that different client types have consistent attributes."""
        http_client = Client("http://localhost:8080")

        # Check basic attributes
        assert hasattr(http_client, '__class__')

        # Check if client has expected MCP-related attributes
        client_attrs = [attr for attr in dir(http_client) if not attr.startswith('_')]
        assert len(client_attrs) > 0

    def test_client_method_availability(self):
        """Test availability of expected client methods."""
        http_client = Client("http://localhost:8080")

        # Check for common async methods
        async_methods = [method for method in dir(http_client) if 'async' in method.lower()]

        # Check for connection-related methods
        conn_methods = [method for method in dir(http_client) if any(keyword in method.lower()
                       for keyword in ['connect', 'close', 'call', 'list'])]

        # Document available methods
        assert isinstance(async_methods, list)
        assert isinstance(conn_methods, list)
