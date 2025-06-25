#!/usr/bin/env python
"""Demo of embedding Magg server in applications.

This example shows how to run Magg server programmatically and
connect to it using the in-memory client.
"""
import asyncio
import logging
import os
import sys

from magg.server.runner import MaggRunner

# Suppress noisy logs for cleaner demo output
logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
logging.getLogger("mcp.server.streamable_http").setLevel(logging.CRITICAL)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.CRITICAL)


async def in_memory_client_example():
    """Example using in-memory client to connect to Magg."""
    print("=== In-Memory Client Example ===")

    # Create runner (uses config from ./.magg/config.json if available)
    async with MaggRunner() as runner:
        # The `async with` simply ensures that the MaggServer is properly set up even when not running as a server.

        # Access the in-memory client
        client = runner.client
        print(f"Client created: {client}")

        # Use the client to interact with Magg
        async with client:
            tools = await client.list_tools()
            print(f"\nFound {len(tools)} tools:")

            # Show first 5 tools
            for tool in tools[:5]:
                print(f"  - {tool.name}: {tool.description}")

            if len(tools) > 5:
                print(f"  ... and {len(tools) - 5} more")

            # Call a tool
            result = await client.call_tool("magg_list_servers", {})
            print(f"\nServers: {result}")

    print("\n")


async def run_http_server():
    """Example of running Magg as an HTTP server."""
    print("=== HTTP Server Example ===")
    print("Starting Magg HTTP server on http://localhost:8080")
    print("Press Ctrl+C to stop\n")

    runner = MaggRunner()

    # This will run until interrupted
    try:
        await runner.run_http(host="localhost", port=8080)
    except KeyboardInterrupt:
        print("\nServer stopped.")


async def concurrent_server_and_client():
    """Example of running server and using client concurrently."""
    print("=== Concurrent Server & Client Example ===")

    runner = MaggRunner()

    stderr_prev = sys.stderr

    try:
        print("Redirecting stderr to /dev/null temporarily to suppress annoying asyncio.CancelledError messages")
        sys.stderr = open(os.devnull, 'w')

        async with runner:
            # Start HTTP server in background
            server_task = await runner.start_http(port=8081)

            # Give server time to start
            await asyncio.sleep(1)

            # Use the in-memory client
            async with runner.client as session:
                print("Connected to Magg server")

                # List and call tools
                tools = await session.list_tools()
                print(f"Available tools: {len(tools)}")

                # Try to call a tool
                try:
                    result = await session.call_tool("magg_list_servers", {})
                    print("Successfully called magg_list_servers")
                except Exception as e:
                    print(f"Tool call error: {e}")

            # Cancel server task
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    finally:
        # sys.stderr.close()
        sys.stderr = stderr_prev

    print("Done\n")


async def main():
    """Run examples."""
    # In-memory client example
    await in_memory_client_example()

    # Concurrent example
    await concurrent_server_and_client()

    # Uncomment to run HTTP server (blocks until Ctrl+C)
    # await run_http_server()


if __name__ == "__main__":
    print("Magg Server Embedding Examples\n")
    asyncio.run(main())
