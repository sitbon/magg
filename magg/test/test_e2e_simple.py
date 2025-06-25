"""Simple E2E test for Magg server without mounting."""

import asyncio
import tempfile
import json
from pathlib import Path
import subprocess
import time
import sys

import pytest
from fastmcp import Client
from magg.settings import ConfigManager, ServerConfig, MaggConfig


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_simple():
    """Test Magg server basic functionality without mounting other servers."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 1. Create Magg config directory
        magg_dir = tmpdir / "magg_test"
        magg_dir.mkdir()
        config_dir = magg_dir / ".magg"
        config_dir.mkdir()

        # 2. Create empty config
        config = MaggConfig()
        config_path = config_dir / "config.json"
        with open(config_path, 'w') as f:
            json.dump({'servers': {}}, f, indent=2)

        # Create empty auth.json to prevent using default keys
        auth_path = config_dir / "auth.json"
        with open(auth_path, 'w') as f:
            json.dump({
                'bearer': {
                    'issuer': 'https://magg.local',
                    'audience': 'test',
                    'key_path': str(tmpdir / 'nonexistent')
                }
            }, f)

        print(f"Config saved to: {config_path}")

        # 3. Start Magg server as subprocess
        magg_script = magg_dir / "run_magg.py"
        magg_script.write_text(f'''
import sys
import os
sys.path.insert(0, "{Path.cwd()}")
os.chdir("{magg_dir}")

from magg.server import MaggServer
import asyncio

async def main():
    server = MaggServer("{config_path}")
    await server.setup()
    print("Magg server started", flush=True)
    await server.mcp.run_http_async(host="localhost", port=54322)

asyncio.run(main())
''')

        # Start Magg
        print("Starting Magg server...")
        magg_proc = subprocess.Popen(
            [sys.executable, str(magg_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait for startup
        started = False
        for i in range(10):  # Try for up to 10 seconds
            if magg_proc.poll() is not None:
                # Process ended
                stdout, stderr = magg_proc.communicate()
                print(f"Magg process ended with code {magg_proc.returncode}")
                print(f"STDOUT:\n{stdout}")
                print(f"STDERR:\n{stderr}")
                pytest.fail(f"Magg server failed to start: {stderr}")

            # Check if server is listening on the port
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', 54322))
            sock.close()

            if result == 0:
                print("Server is listening on port 54322")
                started = True
                break

            time.sleep(1)

        if not started:
            pytest.fail("Magg server didn't start listening on port 54322")

        try:
            # 4. Connect to Magg as client
            print("\nConnecting to Magg...")
            client = Client("http://localhost:54322/mcp/")

            # Use the client in async context
            async with client:
                tools = await client.list_tools()
                tool_names = [tool.name for tool in tools]
                print(f"\nAvailable tools: {tool_names}")

                # Verify Magg's own tools are available
                assert "magg_list_servers" in tool_names
                assert "magg_add_server" in tool_names

                # Test listing servers (should be empty)
                result = await client.call_tool("magg_list_servers", {})
                print(f"\nResult: {result}")

                # Parse the JSON response
                response_text = result[0].text if result else "{}"
                servers_data = json.loads(response_text)
                print(f"Parsed servers data: {servers_data}")

                assert servers_data["output"] == []

                print("\n✅ All tests passed!")

        finally:
            # Cleanup
            magg_proc.terminate()
            magg_proc.wait()


if __name__ == "__main__":
    asyncio.run(test_e2e_simple())
