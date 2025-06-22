#!/usr/bin/env python
"""Demo of using MAGGRunner for embedding MAGG in applications."""
import asyncio
import logging
from magg.client import MAGGRunner

# Suppress uvicorn shutdown errors for cleaner demo output
logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
logging.getLogger("mcp.server.streamable_http").setLevel(logging.CRITICAL)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.CRITICAL)


def basic_examples():
    """Basic usage examples."""
    print("=== Basic Examples ===\n")

    # 1. Simple start/stop
    print("1. Simple start/stop:")
    runner = MAGGRunner(transport="http", port=0)  # auto-assign port
    info = runner.start()
    print(f"   MAGG running at: {info.url}")
    runner.stop()
    print("   Stopped\n")

    # 2. Fixed port example
    print("2. Fixed port example:")
    runner = MAGGRunner(transport="http", port=8888)
    info = runner.start()
    print(f"   MAGG running at: {info.url}")
    runner.stop()
    print("   Stopped\n")


async def async_client_example():
    """Async example with client."""
    print("=== Async Client Example ===")

    # Context manager returns a client
    async with MAGGRunner(transport="http", port=8080) as client:
        print(f"Client: {client}")

        # Use the client directly with its context manager
        async with client as session:
            tools = await session.list_tools()
            print(f"Available tools: {len(tools)} tools")
            # Show first 3 tools
            for i, tool in enumerate(tools[:3]):
                print(f"  {i+1}. {tool.name}: {tool.description}")

    print("Server stopped\n")


async def manual_usage():
    """Show manual start/stop pattern."""
    print("=== Manual Usage ===")

    # Manual async start/stop
    runner = MAGGRunner(transport="http", port=0)  # Auto-assign to avoid conflicts
    info = await runner.astart()

    print(f"Server running at: {info.url}")

    # Access client via cached property
    client = info.client
    print(f"Client: {client}")

    # Use the client
    async with client as session:
        tools = await session.list_tools()
        print(f"Found {len(tools)} tools")

        # Call a tool if available
        if any(t.name == "magg_list_servers" for t in tools):
            try:
                result = await session.call_tool("magg_list_servers", {})
                print(f"Called magg_list_servers successfully")
            except Exception as e:
                print(f"Tool call error: {e}")

    # Stop server
    await runner.astop()
    print("Done\n")


def serve_forever_example():
    """Example of running server continuously."""
    print("\n=== Serve Forever Example ===")
    print("Starting MAGG server...")
    print("Press Ctrl+C to stop\n")

    runner = MAGGRunner(transport="http", port=8080)
    info = runner.start()

    print(f"MAGG server running at: {info.url}")
    print("\nYou can now connect to the server from another process")
    print("Example: client = Client('{}')\n".format(info.url))
    print("Server is running... (press Ctrl+C to stop)")

    try:
        # Block until server stops (cleanly waits on thread)
        runner.join()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        runner.stop()
        print("Server stopped.")


async def async_serve_forever_example():
    """Async version of serve forever."""
    print("\n=== Async Serve Forever Example ===")
    print("Starting MAGG server asynchronously...")
    print("Press Ctrl+C to stop\n")

    runner = MAGGRunner(transport="http", port=8081)
    info = await runner.astart()

    print(f"MAGG server running at: {info.url}")
    print("\nServer is running asynchronously...")

    try:
        # Block until server stops (cleanly waits on task)
        await runner.ajoin()
    except asyncio.CancelledError:
        print("\n\nShutting down...")
        await runner.astop()
        print("Server stopped.")


async def main():
    """Run all async examples."""
    await async_client_example()
    await manual_usage()
    # Uncomment to test async serve forever
    # await async_serve_forever_example()


if __name__ == "__main__":
    # Basic sync examples
    # basic_examples()

    # Async examples (FastMCP clients are async-only)
    print("Note: FastMCP clients require async usage\n")
    asyncio.run(main())

    # Uncomment to test serve_forever
    # serve_forever_example()
