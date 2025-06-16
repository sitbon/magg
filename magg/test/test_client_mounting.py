"""Test client mounting approaches with FastMCP."""

import asyncio
import tempfile
from pathlib import Path

from fastmcp import FastMCP, Client
from magg.utils.custom_transports import NoValidatePythonStdioTransport


async def test_fastmcp_mounting_approaches():
    """Test different approaches to mounting external servers."""
    
    # Create a test server file
    with tempfile.TemporaryDirectory() as tmpdir:
        server_code = '''
from fastmcp import FastMCP

mcp = FastMCP("calculator")

@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@mcp.tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b

if __name__ == "__main__":
    mcp.run()
'''
        server_file = Path(tmpdir) / "calc_server.py"
        server_file.write_text(server_code)
        
        # Create main MAGG server
        magg = FastMCP("magg-test")
        
        print("Testing FastMCP mounting approaches...\n")
        
        # Test 1: Check Client attributes
        print("1. Checking Client attributes:")
        transport = NoValidatePythonStdioTransport(
            script_path=str(server_file),
            cwd=tmpdir
        )
        client = Client(transport)
        
        print(f"   Client type: {type(client)}")
        print(f"   Has _has_lifespan: {hasattr(client, '_has_lifespan')}")
        print(f"   Client attributes with 'mount': {[a for a in dir(client) if 'mount' in a.lower()]}")
        print(f"   Client attributes with 'proxy': {[a for a in dir(client) if 'proxy' in a.lower()]}")
        
        # Test 2: Check FastMCP.from_client result
        print("\n2. Checking FastMCP.from_client:")
        try:
            proxy = FastMCP.from_client(client)
            print(f"   from_client type: {type(proxy)}")
            print(f"   Has _has_lifespan: {hasattr(proxy, '_has_lifespan')}")
            print(f"   Proxy name: {getattr(proxy, 'name', 'N/A')}")
        except Exception as e:
            print(f"   from_client failed: {e}")
        
        # Test 3: Try connecting and listing tools
        print("\n3. Testing client connection:")
        try:
            # Try to connect and list tools
            async with client:
                print("   Client connected successfully")
                
                # Try to list tools
                tools = await client.list_tools()
                print(f"   Found {len(tools)} tools:")
                for tool in tools:
                    print(f"     - {tool.name}")
                    
        except Exception as e:
            print(f"   Client connection failed: {e}")
        
        # Test 4: Alternative - create a wrapper server
        print("\n4. Testing wrapper server approach:")
        
        @magg.tool
        async def calc_add(a: int, b: int) -> int:
            """Add two numbers using the calculator server."""
            async with client:
                result = await client.call_tool("add", {"a": a, "b": b})
                return result
        
        print("   Created wrapper tool: calc_add")
        
        # List MAGG tools
        print("\n5. MAGG server tools:")
        # Get tools from the server
        magg_tools = []
        if hasattr(magg, '_tool_manager'):
            magg_tools = list(magg._tool_manager.tools.keys())
        elif hasattr(magg, 'tools'):
            magg_tools = list(magg.tools.keys()) if hasattr(magg.tools, 'keys') else []
        
        print(f"   Found {len(magg_tools)} tools: {magg_tools}")


if __name__ == "__main__":
    asyncio.run(test_fastmcp_mounting_approaches())