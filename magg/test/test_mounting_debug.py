"""Debug test for FastMCP mounting."""

import asyncio
import pytest
import tempfile
from pathlib import Path

from fastmcp import FastMCP, Client
from magg.util.transports import NoValidatePythonStdioTransport


@pytest.mark.asyncio
async def test_mounting_debug():
    """Debug mounting behavior."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple server
        server_code = '''
from fastmcp import FastMCP

mcp = FastMCP("test")

@mcp.tool
def hello(name: str = "World") -> str:
    """Say hello."""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
'''
        server_file = Path(tmpdir) / "server.py"
        server_file.write_text(server_code)

        # Create main server
        main = FastMCP("main")

        # Add a local tool to main
        @main.tool
        def main_tool() -> str:
            """A tool on the main server."""
            return "This is the main server"

        # Create client and proxy
        transport = NoValidatePythonStdioTransport(
            script_path=str(server_file),
            cwd=tmpdir
        )
        client = Client(transport)
        proxy = FastMCP.as_proxy(client)

        print(f"Created proxy: {type(proxy)}")
        print(f"Proxy has _has_lifespan: {hasattr(proxy, '_has_lifespan')}")

        # Mount the proxy
        main.mount("test", proxy)
        print("Mounted proxy with prefix 'test'")

        # Check what tools are available
        print("\nChecking tools on main server:")

        # Method 1: Check _tool_manager
        if hasattr(main, '_tool_manager'):
            tool_manager = main._tool_manager
            if hasattr(tool_manager, '_tools'):
                tools = tool_manager._tools
                print(f"  _tool_manager._tools: {list(tools.keys())}")

            # Also check for mounted tools
            if hasattr(tool_manager, 'tools'):
                print(f"  _tool_manager.tools: {list(tool_manager.tools.keys())}")

        # Method 2: Test if proxy is working
        print("\nTesting proxy directly:")
        if hasattr(proxy, '_client'):
            print("  Proxy has _client")
            # The proxy should handle the client connection

        # Method 3: Check server state after mounting
        print("\nChecking mounted servers:")
        if hasattr(main, '_mounted_servers'):
            print(f"  _mounted_servers: {list(main._mounted_servers.keys())}")

        # Method 4: Try to access tools through tool manager
        print("\nLooking for prefixed tools:")
        if hasattr(main, '_tool_manager') and hasattr(main._tool_manager, '_tools'):
            all_tools = main._tool_manager._tools
            prefixed_tools = [name for name in all_tools if name.startswith('test')]
            print(f"  Prefixed tools: {prefixed_tools}")

        # Method 5: Test with the actual server running
        print("\nTesting with server run:")
        # We can't easily test the full flow here since it requires running the server
        # But we can check if the mounting was registered

        print("\nMounting appears to have succeeded, but tools may not be available until server is run.")


if __name__ == "__main__":
    asyncio.run(test_mounting_debug())
