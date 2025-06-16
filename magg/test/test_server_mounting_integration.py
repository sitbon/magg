"""Integration test for server mounting with real servers."""

import asyncio
import tempfile
import json
from pathlib import Path

from fastmcp import FastMCP, Client
from magg.server import setup_magg, mount_server, mcp as magg_mcp
from magg.core.config import ConfigManager, MCPSource, MCPServer, MAGGConfig


async def test_full_server_mounting():
    """Test the full server mounting flow with a real MCP server."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Create a test MCP server
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

@mcp.resource("calculator://stats")
def get_stats() -> str:
    """Get calculator statistics."""
    return "Calculator stats: 0 operations performed"

if __name__ == "__main__":
    mcp.run()
'''
        
        # Create source directory structure
        source_dir = Path(tmpdir) / ".magg" / "sources" / "calculator"
        source_dir.mkdir(parents=True)
        
        server_file = source_dir / "server.py"
        server_file.write_text(server_code)
        
        # 2. Set up MAGG configuration
        config_path = Path(tmpdir) / ".magg" / "config.json"
        config = MAGGConfig()
        
        # Add source
        source = MCPSource(
            name="calculator",
            uri=f"file://{source_dir}"
        )
        config.add_source(source)
        
        # Add server
        server = MCPServer(
            name="calc",
            source_name="calculator",
            prefix="calc",
            command="python",
            args=["server.py"],
            working_dir=str(source_dir)
        )
        config.add_server(server)
        
        # Save config
        config_manager = ConfigManager(str(config_path))
        config_manager.save_config(config)
        
        print("Test setup complete. Config saved to:", config_path)
        
        # 3. Initialize MAGG
        await setup_magg(str(config_path))
        print("MAGG initialized")
        
        # 4. Mount the server
        success = await mount_server(server)
        print(f"Server mount {'succeeded' if success else 'failed'}")
        
        # 5. Test the mounted tools
        if success:
            print("\nTesting mounted tools...")
            
            # Get the proxy server
            from magg.server import mounted_servers
            proxy = mounted_servers.get("calc")
            if proxy:
                print(f"Found mounted proxy: {type(proxy)}")
                
                # Try to list tools on the main MAGG server
                print("\nListing tools on MAGG server:")
                # Check different ways to get tools
                if hasattr(magg_mcp, '_tool_manager'):
                    tool_manager = magg_mcp._tool_manager
                    if hasattr(tool_manager, '_tools'):
                        tools = tool_manager._tools
                        calc_tools = [name for name in tools.keys() if name.startswith('calc')]
                        print(f"  Found {len(calc_tools)} calculator tools: {calc_tools}")
                        
                        # Test calling a mounted tool
                        if 'calc_add' in tools:
                            print("\nTesting calc_add tool:")
                            tool = tools['calc_add']
                            # Tool execution would require proper context
                            print(f"  Tool found: {tool}")
                
                # Alternative: Check if we can access the client
                print("\nChecking proxy details:")
                if hasattr(proxy, '_client'):
                    print("  Proxy has _client attribute")
                    client = proxy._client
                    # Try to list tools directly from client
                    try:
                        async with client:
                            tools = await client.list_tools()
                            print(f"  Client has {len(tools)} tools:")
                            for tool in tools:
                                print(f"    - {tool.name}: {tool.description}")
                    except Exception as e:
                        print(f"  Client tool listing failed: {e}")
        
        return success


if __name__ == "__main__":
    success = asyncio.run(test_full_server_mounting())
    print(f"\nTest {'PASSED' if success else 'FAILED'}")