#!/usr/bin/env python3
"""Example of connecting to MCP servers with authentication.

This script demonstrates:
1. Bearer token authentication with configurable environment variables
2. Direct token passing
3. Using the MaggClient for automatic authentication
"""
import argparse
import asyncio
import os
import sys
from typing import Any

from fastmcp import Client
from fastmcp.client import BearerAuth
from magg.client import MaggClient


async def bearer_auth(args: argparse.Namespace) -> None:
    """Test bearer token authentication with configurable options."""
    # Get JWT from environment or command line
    jwt = args.token
    if not jwt:
        jwt = os.environ.get(args.env_var)
        if not jwt:
            print(f"Error: No JWT token provided. Set {args.env_var} or use --token", file=sys.stderr)
            sys.exit(1)

    print(f"Connecting to {args.url} with bearer token authentication...")

    if args.magg:
        # Use MaggClient
        print(f"Using MaggClient{' with provided token' if args.token else f' (loading from {args.env_var})'}")

        # If using custom env var, set MAGG_JWT for MaggClient
        if args.env_var != "MAGG_JWT" and not args.token:
            os.environ["MAGG_JWT"] = jwt

        if args.token:
            auth = BearerAuth(args.token)
            client = MaggClient(args.url, auth=auth)
        else:
            # Let MaggClient handle auth from MAGG_JWT env var
            client = MaggClient(args.url)

        async with client:
            print(f"Transparent proxy mode: {client._transparent}")

            # Test the connection
            await check_client_capabilities(client)

            # Test proxy-specific functionality if available
            try:
                print("\nTesting proxy functionality...")
                tools = await client.proxy("tool", "list")
                print(f"Proxy list returned {len(tools)} items")
            except Exception as e:
                print(f"Proxy functionality not available: {e}")
    else:
        # Use regular FastMCP Client
        print(f"Using FastMCP Client")
        auth = BearerAuth(jwt)

        async with Client(args.url, auth=auth) as client:
            # Test the connection
            await check_client_capabilities(client)


async def check_client_capabilities(client: Any) -> None:
    """Test basic MCP client capabilities."""
    # List available tools
    tools = await client.list_tools()
    print(f"\nFound {len(tools)} tools:")
    for tool in tools[:5]:  # Show first 5 tools
        print(f"  - {tool.name}: {tool.description}")
    if len(tools) > 5:
        print(f"  ... and {len(tools) - 5} more")

    # List resources
    try:
        resources = await client.list_resources()
        print(f"\nFound {len(resources)} resources")
    except Exception as e:
        print(f"\nResource listing not available: {e}")

    # List prompts
    try:
        prompts = await client.list_prompts()
        print(f"\nFound {len(prompts)} prompts")
    except Exception as e:
        print(f"\nPrompt listing not available: {e}")

    # Call a simple tool if available
    if tools:
        # Look for a simple info/status tool
        info_tools = [t for t in tools if "status" in t.name.lower() or "info" in t.name.lower()]
        if info_tools:
            tool = info_tools[0]
            print(f"\nCalling tool: {tool.name}")
            try:
                result = await client.call_tool(tool.name)
                print(f"Result: {result[:200]}..." if len(str(result)) > 200 else f"Result: {result}")
            except Exception as e:
                print(f"Tool call failed: {e}")


def create_parser() -> argparse.ArgumentParser:
    """Create command line parser."""
    parser = argparse.ArgumentParser(
        description="Test MCP server authentication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with bearer token from environment
  %(prog)s bearer

  # Test with custom URL
  %(prog)s bearer http://localhost:9000

  # Test with custom environment variable
  %(prog)s bearer --env-var MY_TOKEN

  # Test with direct token
  %(prog)s bearer --token "eyJ..."

  # Test using MaggClient (auto-loads from MAGG_JWT)
  %(prog)s bearer --magg

  # Test MaggClient with direct token
  %(prog)s bearer --magg --token "eyJ..."
"""
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )

    subparsers = parser.add_subparsers(dest="auth_type", help="Authentication type")

    # Bearer authentication subcommand
    bearer_parser = subparsers.add_parser(
        "bearer",
        help="Test bearer token authentication"
    )
    bearer_parser.add_argument(
        "url",
        nargs="?",
        default="http://localhost:8000/mcp",
        help="MCP server URL (default: http://localhost:8000/mcp)"
    )
    bearer_parser.add_argument(
        "--env-var",
        default="MAGG_JWT",
        help="Environment variable name for JWT (default: MAGG_JWT)"
    )
    bearer_parser.add_argument(
        "--token",
        help="JWT token (overrides environment variable)"
    )
    bearer_parser.add_argument(
        "--magg",
        action="store_true",
        help="Use MaggClient instead of regular FastMCP Client"
    )

    return parser


async def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    # Check if subcommand was provided
    if not args.auth_type:
        parser.print_help()
        sys.exit(1)

    try:
        if args.auth_type == "bearer":
            await bearer_auth(args)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
