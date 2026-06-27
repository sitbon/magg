"""Test real server mounting with FastMCP."""

import pytest
import asyncio
import tempfile
from pathlib import Path

from fastmcp import FastMCP, Client
from fastmcp.server import create_proxy


class TestRealMounting:
    """Test mounting real servers using FastMCP."""

    @pytest.mark.asyncio
    async def test_mount_python_server(self):
        """Test mounting a real Python MCP server."""
        # Create a temporary directory for our test server
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple MCP server
            server_code = '''
from fastmcp import FastMCP

mcp = FastMCP("test-server")

@mcp.tool
def test_tool(message: str) -> str:
    """A test tool."""
    return f"Test server says: {message}"

if __name__ == "__main__":
    mcp.run()
'''
            server_file = Path(tmpdir) / "server.py"
            server_file.write_text(server_code)

            # Create the main Magg server
            main_server = FastMCP("test-magg")

            # Import the custom transport
            from magg.util.transports import NoValidatePythonStdioTransport

            # Mount the backend server as a proxy (how Magg mounts servers)
            transport = NoValidatePythonStdioTransport(
                script_path=str(server_file),
                cwd=tmpdir
            )
            client = Client(transport)
            proxy = create_proxy(client)
            main_server.mount(server=proxy, namespace="test")

            # List tools through the FastMCP client
            async with Client(main_server) as client:
                tools = await client.list_tools()
                tool_names = {tool.name for tool in tools}

            assert "test_test_tool" in tool_names


if __name__ == "__main__":
    # Run the test directly
    test = TestRealMounting()
    asyncio.run(test.test_mount_python_server())
