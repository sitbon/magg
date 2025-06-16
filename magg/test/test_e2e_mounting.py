"""End-to-end test for MAGG server mounting."""

import asyncio
import tempfile
import json
from pathlib import Path
import subprocess
import time
import sys

from fastmcp import Client
from magg.core.config import ConfigManager, MCPSource, MCPServer, MAGGConfig


async def test_e2e_mounting():
    """Test MAGG with real server mounting end-to-end."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # 1. Create a calculator MCP server
        calc_dir = tmpdir / "calculator"
        calc_dir.mkdir()
        
        calc_server = calc_dir / "server.py"
        calc_server.write_text('''
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
''')
        
        # 2. Create MAGG config
        magg_dir = tmpdir / "magg_test"
        magg_dir.mkdir()
        config_dir = magg_dir / ".magg"
        config_dir.mkdir()
        
        config = MAGGConfig()
        
        # Add calculator source
        source = MCPSource(
            name="calculator",
            uri=f"file://{calc_dir}"
        )
        config.add_source(source)
        
        # Add calculator server
        server = MCPServer(
            name="calc",
            source_name="calculator",
            prefix="calc",
            command="python",
            args=["server.py"],
            working_dir=str(calc_dir)
        )
        config.add_server(server)
        
        # Save config
        config_path = config_dir / "config.json"
        with open(config_path, 'w') as f:
            json.dump({
                'sources': {s.name: {'name': s.name, 'uri': s.uri} for s in [source]},
                'servers': {s.name: {
                    'name': s.name,
                    'source_name': s.source_name,
                    'prefix': s.prefix,
                    'command': s.command,
                    'args': s.args,
                    'working_dir': s.working_dir
                } for s in [server]}
            }, f, indent=2)
        
        print(f"Config saved to: {config_path}")
        
        # 3. Start MAGG server as subprocess
        magg_script = magg_dir / "run_magg.py"
        magg_script.write_text(f'''
import sys
import os
sys.path.insert(0, "{Path.cwd()}")
os.chdir("{magg_dir}")

from magg.server import setup_magg, mcp
import asyncio

async def main():
    await setup_magg()
    await mcp.run_async(transport="stdio")

if __name__ == "__main__":
    asyncio.run(main())
''')
        
        try:
            # 3. Connect to MAGG as a client using custom transport
            print("\nConnecting to MAGG...")
            from magg.utils.custom_transports import NoValidatePythonStdioTransport
            transport = NoValidatePythonStdioTransport(
                script_path=str(magg_script),
                python_cmd=sys.executable,
                cwd=str(magg_dir)
            )
            client = Client(transport)
            
            async with client:
                print("Connected to MAGG")
                
                # List tools
                tools = await client.list_tools()
                print(f"\nFound {len(tools)} tools:")
                for tool in tools:
                    print(f"  - {tool.name}: {tool.description}")
                
                # Filter for calculator tools
                calc_tools = [t for t in tools if t.name.startswith('calc')]
                print(f"\nCalculator tools: {[t.name for t in calc_tools]}")
                
                # Test calling a calculator tool
                if any(t.name == 'calc_add' for t in tools):
                    print("\nTesting calc_add(5, 3):")
                    result = await client.call_tool('calc_add', {'a': 5, 'b': 3})
                    print(f"  Result: {result}")
                    
                    print("\nTesting calc_multiply(4, 7):")
                    result = await client.call_tool('calc_multiply', {'a': 4, 'b': 7})
                    print(f"  Result: {result}")
                else:
                    print("\nWARNING: calc_add tool not found!")
                
                # Also test MAGG's own tools
                magg_tools = [t for t in tools if t.name.startswith('magg_')]
                print(f"\nMAGG tools: {[t.name for t in magg_tools][:5]}...")  # First 5
                
                return len(calc_tools) > 0
                
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_e2e_mounting())
    print(f"\nTest {'PASSED' if success else 'FAILED'}: {'Found' if success else 'Did not find'} calculator tools")