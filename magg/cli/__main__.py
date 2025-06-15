#!/usr/bin/env python3
"""Main CLI interface for MAGG - Simplified implementation."""

import argparse
import asyncio
import json
import sys
import logging
from pathlib import Path

from magg.core.config import ConfigManager, MCPSource, MCPServer


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


async def cmd_serve(args) -> None:
    """Start MAGG server."""
    try:
        from magg.server import mcp, setup_magg
    except ImportError as e:
        print(f"❌ Failed to import server components: {e}", file=sys.stderr)
        print("💡 Make sure FastMCP is installed: pip install fastmcp", file=sys.stderr)
        sys.exit(1)
    
    await setup_magg(args.config)
    
    if args.http:
        print(f"🚀 Starting MAGG HTTP server on {args.host}:{args.port}", file=sys.stderr)
        print(f"📡 Server URL: http://{args.host}:{args.port}", file=sys.stderr)
        print(f"🔧 Available tools: {len(await mcp.get_tools())}", file=sys.stderr)
        print("Press Ctrl+C to stop...", file=sys.stderr)
        
        try:
            await mcp.run_http_async(host=args.host, port=args.port)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down MAGG HTTP server...", file=sys.stderr)
    else:
        print("🚀 Starting MAGG in stdio mode", file=sys.stderr)
        print(f"🔧 Available tools: {len(await mcp.get_tools())}", file=sys.stderr)
        print("Ready for MCP client connections...", file=sys.stderr)
        
        try:
            await mcp.run_stdio_async()
        except KeyboardInterrupt:
            print("\n🛑 Shutting down MAGG server...", file=sys.stderr)


async def cmd_add_source(args) -> None:
    """Add a new MCP source."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()
    
    if args.url in config.sources:
        print(f"⚠️ Source with URL '{args.url}' already exists: {config.sources[args.url].name}")
        choice = input("Continue anyway? (y/N): ").lower().strip()
        if choice != 'y':
            print("Cancelled")
            return
    
    source = MCPSource(url=args.url, name=args.name)
    config.add_source(source)
    
    if config_manager.save_config(config):
        print(f"✅ Added source '{source.name}'")
        print(f"📍 URL: {args.url}")
        print(f"💡 Use 'magg add-server' to create a runnable server from this source")
    else:
        print(f"❌ Failed to save configuration")
        sys.exit(1)


async def cmd_add_server(args) -> None:
    """Add a new MCP server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()
    
    if args.source_url not in config.sources:
        print(f"❌ Source '{args.source_url}' not found. Add it first with 'magg add-source'")
        sys.exit(1)
    
    if args.name in config.servers:
        print(f"❌ Server '{args.name}' already exists")
        sys.exit(1)
    
    # Parse environment variables
    env = None
    if args.env:
        env = dict(arg.split('=', 1) for arg in args.env)
    
    server = MCPServer(
        name=args.name,
        source_url=args.source_url,
        prefix=args.prefix or args.name,
        command=args.command.split() if args.command else None,
        uri=args.uri,
        env=env,
        working_dir=args.working_dir,
        notes=args.notes
    )
    
    config.add_server(server)
    
    if config_manager.save_config(config):
        print(f"✅ Added server '{args.name}'")
        print(f"📍 Source: {args.source_url}")
        print(f"🏷️ Prefix: {server.prefix}")
        if server.command:
            print(f"▶️ Command: {' '.join(server.command)}")
        if server.notes:
            print(f"📝 Notes: {server.notes}")
        print(f"💡 Server is now mounted and ready to use")
    else:
        print(f"❌ Failed to save configuration")
        sys.exit(1)




async def cmd_list_sources(args) -> None:
    """List configured sources."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()
    
    if not config.sources:
        print("📭 No sources configured")
        return
    
    print("📦 Sources:")
    for url, source in config.sources.items():
        servers = config.get_servers_for_source(url)
        server_count = len(servers)
        
        print(f"  📦 {source.name}")
        print(f"      URL: {url}")
        print(f"      Servers: {server_count}")
        print()


async def cmd_list_servers(args) -> None:
    """List configured servers."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()
    
    if not config.servers:
        print("📭 No servers configured")
        return
    
    print("🖥️ Servers:")
    for name, server in config.servers.items():
        print(f"  🖥️ {name} ({server.prefix})")
        print(f"      Source: {server.source_url}")
        
        if server.command:
            print(f"      Command: {' '.join(server.command)}")
        if server.uri:
            print(f"      URI: {server.uri}")
        if server.working_dir:
            print(f"      Working Dir: {server.working_dir}")
        if server.notes:
            print(f"      Notes: {server.notes}")
        print()


async def cmd_search_sources(args) -> None:
    """Search for MCP sources."""
    try:
        from magg.discovery.catalog import CatalogManager
    except ImportError as e:
        print(f"❌ Failed to import discovery components: {e}", file=sys.stderr)
        print("💡 Make sure required dependencies are installed", file=sys.stderr)
        sys.exit(1)
    
    catalog_manager = CatalogManager()
    
    print(f"🔍 Searching for '{args.query}'...")
    results = await catalog_manager.search_only(args.query, args.limit)
    
    if not any(results.values()):
        print("❌ No results found")
        return
    
    print("📦 Search Results:")
    result_index = 1
    
    for source, source_results in results.items():
        if source_results:
            print(f"\n📂 {source.upper()}:")
            for result in source_results:
                print(f"   [{result_index}] {result.name}")
                print(f"       {result.description}")
                if result.url:
                    print(f"       🔗 {result.url}")
                if result.install_command:
                    print(f"       📦 {result.install_command}")
                if result.rating:
                    print(f"       ⭐ {result.rating}")
                
                result_index += 1
                print()
    
    print("💡 To add a source:")
    print("   magg add-source <url> <name>")


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        description="MAGG - MCP Aggregator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start MAGG in stdio mode (default)
  magg

  # Start MAGG as HTTP server
  magg --http --port 8080

  # Add a source
  magg add-source https://github.com/example/weather-mcp weather

  # Add and mount a server from source
  magg add-server weather_server https://github.com/example/weather-mcp --command "./weather-server"

  # Search for sources
  magg search-sources calculator
        """
    )
    
    # Global options
    parser.add_argument(
        '--config', '-c',
        type=str,
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )
    
    # Server mode options (for the default serve command)
    parser.add_argument(
        '--http',
        action='store_true',
        help='Run as HTTP server instead of stdio'
    )
    
    parser.add_argument(
        '--host',
        default='localhost',
        help='HTTP server host (default: localhost)'
    )
    
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8080,
        help='HTTP server port (default: 8080)'
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='subcommand', help='Available commands')
    
    # Add source command
    add_source_parser = subparsers.add_parser('add-source', help='Add a new MCP source')
    add_source_parser.add_argument('url', help='Source URL')
    add_source_parser.add_argument('name', nargs='?', help='Source name (optional)')
    
    # Add server command
    add_server_parser = subparsers.add_parser('add-server', help='Add a new MCP server')
    add_server_parser.add_argument('name', help='Server name')
    add_server_parser.add_argument('source_url', help='Source URL')
    add_server_parser.add_argument('--prefix', help='Tool prefix (defaults to server name)')
    add_server_parser.add_argument('--command', help='Command to run')
    add_server_parser.add_argument('--uri', help='URI for HTTP servers')
    add_server_parser.add_argument('--env', action='append', help='Environment variables (KEY=VALUE)')
    add_server_parser.add_argument('--working-dir', help='Working directory')
    add_server_parser.add_argument('--notes', help='Setup notes')
    
    # List commands
    list_sources_parser = subparsers.add_parser('list-sources', help='List configured sources')
    list_servers_parser = subparsers.add_parser('list-servers', help='List configured servers')
    
    # Search sources command
    search_parser = subparsers.add_parser('search-sources', help='Search for MCP sources')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--limit', type=int, default=5, help='Results per source (default: 5)')
    
    return parser


async def main_async() -> None:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    # If no command is specified, default to serve
    if not args.subcommand:
        await cmd_serve(args)
        return
    
    # Map commands to functions
    command_map = {
        'add-source': cmd_add_source,
        'add-server': cmd_add_server,
        'list-sources': cmd_list_sources,
        'list-servers': cmd_list_servers,
        'search-sources': cmd_search_sources,
    }
    
    command_func = command_map.get(args.subcommand)
    if command_func:
        try:
            await command_func(args)
        except KeyboardInterrupt:
            print("\n🛑 Operation cancelled")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    else:
        print(f"❌ Unknown command: {args.subcommand}")
        sys.exit(1)


def main():
    """Sync entry point for CLI."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 Interrupted")
        sys.exit(1)


if __name__ == "__main__":
    main()