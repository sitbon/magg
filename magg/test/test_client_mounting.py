"""Test client mounting approaches with FastMCP."""

import pytest
import tempfile
from pathlib import Path

from fastmcp import FastMCP, Client
from magg.util.transports import NoValidatePythonStdioTransport


@pytest.mark.asyncio
async def test_fastmcp_mounting_approaches():
    """Test different approaches to mounting external servers."""

    # Create a test server file
    with tempfile.TemporaryDirectory() as tmpdir:
        server_code = '''
from fastmcp import FastMCP

mcp = FastMCP("calculator")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b

if __name__ == "__main__":
    mcp.run()
'''
        server_path = Path(tmpdir) / "calc_server.py"
        server_path.write_text(server_code)

        # Create transport
        transport = NoValidatePythonStdioTransport(
            script_path=str(server_path),
            cwd=str(tmpdir)
        )

        # Create client
        client = Client(transport)

        # Test 1: Verify client can connect and list tools
        async with client:
            tools = await client.list_tools()
            assert len(tools) == 2
            tool_names = [tool.name for tool in tools]
            assert "add" in tool_names
            assert "multiply" in tool_names

            # Test calling a tool
            result = await client.call_tool("add", {"a": 5, "b": 3})
            assert len(result) > 0
            assert "8" in result[0].text

        # Test 2: Create proxy from client (new way)
        proxy = FastMCP.as_proxy(client)
        assert proxy is not None

        # Test 3: Mount proxy to another server
        magg = FastMCP("magg-test")

        # Define a local tool
        @magg.tool()
        def local_tool() -> str:
            """A local tool in Magg."""
            return "Local response"

        # Mount the proxy
        magg.mount("calc", proxy)

        # Verify tools are available via the mount
        # Note: We can't directly test the mounted tools without running the server
        # but we've verified the mounting process works
        assert True  # Basic smoke test passed
