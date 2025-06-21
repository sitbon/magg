"""Unit tests for transport utilities."""

from unittest.mock import patch, MagicMock
import tempfile
import os

from magg.util.transport import get_transport_for_command, get_transport_for_uri
from magg.util.transports import NoValidatePythonStdioTransport, NoValidateNodeStdioTransport
from fastmcp.client.transports import (
    StdioTransport,
    NpxStdioTransport,
    UvxStdioTransport,
    SSETransport,
    StreamableHttpTransport
)


class TestGetTransportForCommand:
    """Test command-based transport selection."""

    def test_python_command_with_script(self):
        """Test Python transport for script execution."""
        # Create a temporary script file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("print('test')")
            script_path = f.name

        try:
            transport = get_transport_for_command(
                command="python",
                args=[script_path, "--port", "8080"],
                working_dir="/tmp/test"
            )

            assert isinstance(transport, NoValidatePythonStdioTransport)
            # Check that transport was configured correctly
            assert transport.command.endswith("python") or transport.command.endswith("python3")
            assert transport.args == [script_path, "--port", "8080"]
            assert transport.cwd == "/tmp/test"
        finally:
            os.unlink(script_path)

    def test_python_command_with_module(self):
        """Test Python transport for module execution (-m)."""
        # Our custom transport doesn't validate, so -m works fine
        transport = get_transport_for_command(
            command="python",
            args=["-m", "mymodule.server", "--debug"],
            working_dir="/tmp/test"
        )

        assert isinstance(transport, NoValidatePythonStdioTransport)
        # Check that transport was configured correctly
        assert transport.command.endswith("python") or transport.command.endswith("python3")
        assert transport.args == ["-m", "mymodule.server", "--debug"]
        assert transport.cwd == "/tmp/test"

    def test_python_command_with_transport_config(self):
        """Test Python transport with custom config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("print('test')")
            script_path = f.name

        try:
            transport = get_transport_for_command(
                command="python",
                args=[script_path],
                transport_config={"python_cmd": "/usr/bin/python3.11", "keep_alive": False}
            )

            assert isinstance(transport, NoValidatePythonStdioTransport)
            # Check the command includes the custom python
            assert transport.command == "/usr/bin/python3.11"
            assert transport.keep_alive is False
        finally:
            os.unlink(script_path)

    def test_node_command(self):
        """Test Node.js transport."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write("console.log('test')")
            script_path = f.name

        try:
            transport = get_transport_for_command(
                command="node",
                args=[script_path, "--experimental-modules"],
                env={"NODE_ENV": "production"}
            )

            assert isinstance(transport, NoValidateNodeStdioTransport)
            assert transport.command == "node"
            assert transport.args == [script_path, "--experimental-modules"]
            assert transport.env == {"NODE_ENV": "production"}
        finally:
            os.unlink(script_path)

    def test_npx_command(self):
        """Test NPX transport."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transport = get_transport_for_command(
                command="npx",
                args=["@modelcontextprotocol/server-calculator"],
                working_dir=tmpdir
            )

            assert isinstance(transport, NpxStdioTransport)
            # NpxStdioTransport has different attributes than other transports
            assert transport.package == "@modelcontextprotocol/server-calculator"

    def test_uvx_command(self):
        """Test UVX transport."""
        transport = get_transport_for_command(
            command="uvx",
            args=["myserver", "--config", "prod.conf"],
            transport_config={"python_version": "3.11", "with_packages": ["requests"]}
        )

        assert isinstance(transport, UvxStdioTransport)
        # UvxStdioTransport builds the command internally
        assert transport.command == "uvx"
        # Check args include the tool and python version
        assert "myserver" in transport.args
        assert "--python" in transport.args
        assert "3.11" in transport.args

    def test_generic_command(self):
        """Test fallback to generic StdioTransport."""
        transport = get_transport_for_command(
            command="/usr/local/bin/custom-server",
            args=["--mode", "production"],
            env={"CUSTOM_VAR": "value"}
        )

        assert isinstance(transport, StdioTransport)
        assert transport.command == "/usr/local/bin/custom-server"
        assert transport.args == ["--mode", "production"]
        assert transport.env == {"CUSTOM_VAR": "value"}


class TestGetTransportForUri:
    """Test URI-based transport selection."""

    def test_sse_endpoint(self):
        """Test SSE transport for /sse endpoints."""
        transport = get_transport_for_uri("http://localhost:8080/sse")
        assert isinstance(transport, SSETransport)
        assert str(transport.url) == "http://localhost:8080/sse"

    def test_sse_endpoint_with_trailing_slash(self):
        """Test SSE transport for /sse/ endpoints."""
        transport = get_transport_for_uri("https://api.example.com/v1/sse/")
        assert isinstance(transport, SSETransport)

    def test_http_endpoint(self):
        """Test StreamableHttpTransport for regular HTTP."""
        transport = get_transport_for_uri("http://localhost:3000")
        assert isinstance(transport, StreamableHttpTransport)
        assert str(transport.url) == "http://localhost:3000"

    def test_https_endpoint(self):
        """Test StreamableHttpTransport for HTTPS."""
        transport = get_transport_for_uri("https://api.example.com/mcp")
        assert isinstance(transport, StreamableHttpTransport)

    def test_uri_with_auth(self):
        """Test transport with authentication config."""
        transport = get_transport_for_uri(
            "https://api.example.com/mcp",
            transport_config={
                "auth": "Bearer token123",
                "headers": {"X-Custom": "value"}
            }
        )

        assert isinstance(transport, StreamableHttpTransport)
        # Auth is converted to an auth object, not kept as string
        assert transport.auth is not None
        assert transport.headers == {"X-Custom": "value"}

    @patch('magg.util.transport.infer_transport')
    def test_unknown_uri_scheme(self, mock_infer):
        """Test fallback to infer_transport for unknown schemes."""
        mock_transport = MagicMock()
        mock_infer.return_value = mock_transport

        result = get_transport_for_uri("custom://some-uri")

        mock_infer.assert_called_once_with("custom://some-uri")
        assert result == mock_transport
