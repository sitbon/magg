"""Test real server mounting with FastMCP."""

import pytest
import asyncio
import tempfile
from pathlib import Path

from fastmcp import FastMCP, Client


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

            # Try different approaches to mount the server

            # Import the custom transport
            from magg.util.transports import NoValidatePythonStdioTransport

            # Approach 1: Using Client with custom transport
            try:
                transport = NoValidatePythonStdioTransport(
                    script_path=str(server_file),
                    cwd=tmpdir
                )
                client = Client(transport)
                # Try to mount the client directly
                main_server.mount("test1", client)
                print("✓ Direct client mount succeeded")
            except Exception as e:
                print(f"✗ Direct client mount failed: {e}")

            # Approach 2: Try with proxy flag
            try:
                transport = NoValidatePythonStdioTransport(
                    script_path=str(server_file),
                    cwd=tmpdir
                )
                client = Client(transport)
                main_server.mount("test2", client, as_proxy=True)
                print("✓ Client mount with as_proxy=True succeeded")
            except Exception as e:
                print(f"✗ Client mount with as_proxy=True failed: {e}")

            # Approach 3: Try as_proxy (new way)
            try:
                transport = NoValidatePythonStdioTransport(
                    script_path=str(server_file),
                    cwd=tmpdir
                )
                client = Client(transport)
                proxy = FastMCP.as_proxy(client)
                main_server.mount("test3", proxy)
                print("✓ as_proxy mount succeeded")
            except Exception as e:
                print(f"✗ as_proxy mount failed: {e}")

            # Get tool names through client
            print("\nAvailable tools on main server:")
            # List tools through the FastMCP client
            async with Client(main_server) as client:
                tools = await client.list_tools()
                for tool in tools:
                    print(f"  - {tool.name}")


if __name__ == "__main__":
    # Run the test directly
    test = TestRealMounting()
    asyncio.run(test.test_mount_python_server())
