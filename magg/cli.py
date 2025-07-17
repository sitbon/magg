#!/usr/bin/env python3
"""Main CLI interface for Magg - Simplified implementation."""

import argparse
import asyncio
import json
import logging
import os
import sys
import traceback
from pathlib import Path

from . import __version__, process
from .auth import BearerAuthManager
from .kit import KitManager
from .settings import ConfigManager, ServerConfig, BearerAuthConfig, AuthConfig, KitInfo

try:
    from cryptography.hazmat.primitives import serialization
except ImportError:
    serialization = None
from .server.runner import MaggRunner
from .util.terminal import (
    print_success, print_error, print_warning, print_startup_banner,
    print_info, print_server_list, print_status_summary, confirm_action,
    print_newline
)

process.setup(source=__name__)

logger: logging.Logger | None = logging.getLogger(__name__)


async def cmd_serve(args) -> None:
    """Start Magg server."""

    logger.info("Starting Magg server (mode: %s)", 'http' if args.http else 'stdio')

    if args.http:
        print_startup_banner()

    runner = MaggRunner(args.config)

    if args.http:
        logger.info("Starting HTTP server on %s:%s", args.host, args.port)
        await runner.run_http(host=args.host, port=args.port)
    else:
        logger.info("Starting stdio server")
        await runner.run_stdio()


def cmd_serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '--http',
        action='store_true',
        help='Run as HTTP server instead of stdio mode'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='localhost',
        help='HTTP server host address (default: localhost)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='HTTP server port (default: 8000)'
    )


async def cmd_add_server(args) -> None:
    """Add a new MCP server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name in config.servers:
        logger.debug("Attempt to add duplicate server: %s", args.name)
        print_error(f"Server '{args.name}' already exists")
        sys.exit(1)

    # Parse environment variables
    env = None
    if args.env:
        try:
            env = dict(arg.split('=', 1) for arg in args.env)
        except ValueError:
            print_error("Invalid environment variable format. Use KEY=VALUE")
            sys.exit(1)

    # Parse command and args
    command = None
    command_args = None
    if args.command:
        parts = args.command.split()
        if parts:
            command = parts[0]
            command_args = parts[1:] if len(parts) > 1 else None

    try:
        server = ServerConfig(
            name=args.name,
            source=args.source,
            prefix=args.prefix,  # Will be auto-generated if not provided
            command=command,
            args=command_args,
            uri=args.uri,
            env=env,
            cwd=args.cwd,
            notes=args.notes
        )
    except ValueError as e:
        print_error(f"Invalid server configuration: {e}")
        sys.exit(1)

    config.add_server(server)

    if config_manager.save_config(config):
        print_success(f"Added server '{args.name}'")
        print(f"  Source: {args.source}")
        print(f"  Prefix: {server.prefix}")
        if server.command:
            full_command = server.command
            if server.args:
                full_command += ' ' + ' '.join(server.args)
            print(f"  Command: {full_command}")
        if server.notes:
            print(f"  Notes: {server.notes}")
    else:
        print_error("Failed to save configuration")
        sys.exit(1)


async def cmd_list_servers(args) -> None:
    """List configured servers."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    # logger.debug("Listing %d configured servers", len(config.servers))
    print_server_list(config.servers)


async def cmd_remove_server(args) -> None:
    """Remove a server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name not in config.servers:
        logger.warning("Attempt to remove non-existent server: %s", args.name)
        print_error(f"Server '{args.name}' not found")
        sys.exit(1)

    # Show server details before removal
    server = config.servers[args.name]
    print_info(
        f"Server to remove: {args.name}\n"
        f"  Source: {server.source}\n"
        f"  Prefix: {server.prefix}"
    )

    if not args.force and not confirm_action("Are you sure you want to remove this server?"):
        logger.debug("User cancelled removal of server '%s'", args.name)
        print_info("Removal cancelled")
        return

    config.remove_server(args.name)

    if config_manager.save_config(config):
        logger.info("Successfully removed server '%s'", args.name)
        print_success(f"Removed server '{args.name}'")
    else:
        print_error("Failed to save configuration")
        sys.exit(1)


async def cmd_enable_server(args) -> None:
    """Enable a server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name not in config.servers:
        print_error(f"Server '{args.name}' not found")
        sys.exit(1)

    server = config.servers[args.name]
    if server.enabled:
        print_info(f"Server '{args.name}' is already enabled")
        return

    server.enabled = True

    if config_manager.save_config(config):
        print_success(
            f"Enabled server '{args.name}'\n"
            "The server will be mounted on next startup"
        )
    else:
        print_error("Failed to save configuration")
        sys.exit(1)


async def cmd_disable_server(args) -> None:
    """Disable a server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name not in config.servers:
        print_error(f"Server '{args.name}' not found")
        sys.exit(1)

    server = config.servers[args.name]
    if not server.enabled:
        print_info(f"Server '{args.name}' is already disabled")
        return

    server.enabled = False

    if config_manager.save_config(config):
        print_success(
            f"Disabled server '{args.name}'\n"
            "If Magg is running, the server will be automatically unmounted"
        )
    else:
        print_error("Failed to save configuration")
        sys.exit(1)


async def cmd_status(args) -> None:
    """Show Magg status."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    enabled = [s for s in config.servers.values() if s.enabled]
    disabled = [s for s in config.servers.values() if not s.enabled]

    print_status_summary(
        str(config_manager.config_path),
        len(config.servers),
        len(enabled),
        len(disabled)
    )


async def cmd_export(args) -> None:
    """Export configuration."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    export_data = {
        'servers': {
            name: server.model_dump(
                mode="json",
                exclude_none=True, exclude_unset=True, exclude_defaults=True, by_alias=True
            )
            for name, server in config.servers.items()
        }
    }

    if args.output:
        try:
            with open(args.output, 'w') as f:
                json.dump(export_data, f, indent=2)
            print_success(f"Exported configuration to {args.output}")
        except IOError as e:
            print_error(f"Failed to write to {args.output}: {e}")
            sys.exit(1)
    else:
        print(json.dumps(export_data, indent=2))


async def cmd_kit(args) -> None:
    """Manage kits."""

    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()
    kit_manager = KitManager(config_manager)

    if args.kit_action == 'list':
        # List available kits
        discovered = kit_manager.discover_kits()
        if not discovered:
            print_warning("No kits found in kit.d directories")
            print_info(f"Search paths: {', '.join(str(p) for p in kit_manager.kitd_paths)}")
            return

        print_info(f"Available kits ({len(discovered)}):")
        for kit_name, kit_path in discovered.items():
            # Try to load to get description
            kit_config = kit_manager.load_kit(kit_path)
            if kit_config and kit_config.description:
                print(f"  • {kit_name}: {kit_config.description}")
            else:
                print(f"  • {kit_name}")

    elif args.kit_action == 'load':
        # Load a kit into configuration
        discovered = kit_manager.discover_kits()
        if args.name not in discovered:
            print_error(f"Kit '{args.name}' not found")
            print_info(f"Available kits: {', '.join(discovered.keys())}")
            sys.exit(1)

        kit_path = discovered[args.name]
        kit_config = kit_manager.load_kit(kit_path)
        if not kit_config:
            print_error(f"Failed to load kit '{args.name}'")
            sys.exit(1)

        # Add kit to config's kits list if not already there
        if args.name not in config.kits:
            config.kits[args.name] = KitInfo(
                name=args.name,
                description=kit_config.description,
                path=str(kit_path),
                source="file"
            )

        # Add servers from kit to configuration
        added_servers = []
        skipped_servers = []
        for server_name, server_config in kit_config.servers.items():
            if server_name in config.servers:
                skipped_servers.append(server_name)
                continue

            # Only override enabled state if --enable/--no-enable was explicitly set
            # Default to kit's enabled state if not specified
            if args.enable is not None:
                server_config.enabled = args.enable
            
            # Track which kit this server came from
            server_config.kits = [args.name]
            
            config.servers[server_name] = server_config
            added_servers.append(server_name)

        # Save configuration
        if config_manager.save_config(config):
            if added_servers:
                print_success(f"Added {len(added_servers)} servers from kit '{args.name}':")
                for name in added_servers:
                    status = "enabled" if config.servers[name].enabled else "disabled"
                    print(f"  • {name} ({status})")
            if skipped_servers:
                print_warning(f"Skipped {len(skipped_servers)} servers already in configuration:")
                for name in skipped_servers:
                    print(f"  • {name}")
            if not added_servers and not skipped_servers:
                print_warning(f"Kit '{args.name}' contains no servers")
        else:
            print_error("Failed to save configuration")
            sys.exit(1)

    elif args.kit_action == 'info':
        # Show information about a kit
        discovered = kit_manager.discover_kits()
        if args.name not in discovered:
            print_error(f"Kit '{args.name}' not found")
            print_info(f"Available kits: {', '.join(discovered.keys())}")
            sys.exit(1)

        kit_path = discovered[args.name]
        kit_config = kit_manager.load_kit(kit_path)
        if not kit_config:
            print_error(f"Failed to load kit '{args.name}'")
            sys.exit(1)

        # Build kit info
        kit_info_lines = [f"Kit: {kit_config.name}"]
        if kit_config.description:
            kit_info_lines.append(f"Description: {kit_config.description}")
        if kit_config.author:
            kit_info_lines.append(f"Author: {kit_config.author}")
        if kit_config.version:
            kit_info_lines.append(f"Version: {kit_config.version}")
        if kit_config.keywords:
            kit_info_lines.append(f"Keywords: {', '.join(kit_config.keywords)}")
        
        print_info("\n".join(kit_info_lines))
        if kit_config.links:
            print("Links:")
            for key, url in kit_config.links.items():
                print(f"  • {key}: {url}")

        if kit_config.servers:
            print(f"\nServers ({len(kit_config.servers)}):")
            for server_name, server in kit_config.servers.items():
                prefix_info = f" (prefix: {server.prefix})" if server.prefix else ""
                print(f"  • {server_name}{prefix_info}")
                if server.notes:
                    print(f"    {server.notes}")
        else:
            print("\nNo servers in this kit")
            
    elif args.kit_action == 'export':
        # Export servers as a kit
        if args.kit:
            # Export a specific loaded kit
            if args.kit not in config.kits:
                print_error(f"Kit '{args.kit}' is not loaded")
                sys.exit(1)
            
            # Load the kit to get its servers
            kit_manager.load_kits_from_config(config)
            servers_to_export = kit_manager.get_kit_servers(args.kit)
            
            # Use existing kit metadata if available
            kit_info = config.kits[args.kit]
            export_name = args.name or kit_info.name
            export_description = args.description or kit_info.description or ""
        else:
            # Export current config servers
            servers_to_export = config.servers
            export_name = args.name or "exported"
            export_description = args.description or "Exported from current configuration"
        
        # Build kit data
        kit_data = {
            "name": export_name,
            "description": export_description,
            "servers": {}
        }
        
        if args.author:
            kit_data["author"] = args.author
        if args.version:
            kit_data["version"] = args.version
        
        # Add servers
        for name, server in servers_to_export.items():
            server_data = server.model_dump(
                mode="json",
                exclude_none=True, exclude_unset=True, exclude_defaults=True,
                by_alias=True,
                exclude={'name', 'kits'}  # Exclude fields not needed in kit
            )
            kit_data["servers"][name] = server_data
        
        # Output
        if args.output:
            try:
                with open(args.output, 'w') as f:
                    json.dump(kit_data, f, indent=2)
                print_success(f"Exported kit to {args.output}")
            except IOError as e:
                print_error(f"Failed to write to {args.output}: {e}")
                sys.exit(1)
        else:
            print(json.dumps(kit_data, indent=2))
            
    else:
        print_error(f"Unknown kit action: {args.kit_action}")
        sys.exit(1)


async def cmd_server(args) -> None:
    """Manage servers."""
    if args.server_action == 'list':
        await cmd_list_servers(args)
    elif args.server_action == 'add':
        await cmd_add_server(args)
    elif args.server_action == 'remove':
        await cmd_remove_server(args)
    elif args.server_action == 'enable':
        await cmd_enable_server(args)
    elif args.server_action == 'disable':
        await cmd_disable_server(args)
    elif args.server_action == 'info':
        await cmd_server_info(args)
    else:
        print_error(f"Unknown server action: {args.server_action}")
        sys.exit(1)


async def cmd_server_info(args) -> None:
    """Show detailed information about a server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name not in config.servers:
        print_error(f"Server '{args.name}' not found")
        sys.exit(1)

    server = config.servers[args.name]

    # Build info text
    info_lines = [
        f"Server: {server.name}",
        f"Source: {server.source}",
        f"Enabled: {'Yes' if server.enabled else 'No'}",
        f"Prefix: {server.prefix if server.prefix else '(none)'}"
    ]
    
    if server.command:
        info_lines.append(f"Command: {server.command}")
        if server.args:
            info_lines.append(f"Arguments: {' '.join(server.args)}")
    
    if server.uri:
        info_lines.append(f"URI: {server.uri}")
    
    if server.cwd:
        info_lines.append(f"Working Directory: {server.cwd}")
    
    print_info("\n".join(info_lines))

    if server.env:
        print("Environment Variables:")
        for key, value in server.env.items():
            print(f"  {key}={value}")

    if server.transport:
        print("Transport Configuration:")
        print(f"  {json.dumps(server.transport, indent=2)}")

    if server.notes:
        print(f"\nNotes: {server.notes}")

    if server.kits:
        print(f"\nIncluded in kits: {', '.join(server.kits)}")


async def cmd_config(args) -> None:
    """Manage configuration."""
    if args.config_action == 'show':
        await cmd_status(args)
    elif args.config_action == 'export':
        await cmd_export(args)
    elif args.config_action == 'path':
        await cmd_config_path(args)


async def cmd_config_path(args) -> None:
    """Show configuration file path."""
    config_manager = ConfigManager(args.config)
    print_info("Configuration file path:")
    print(f"  {config_manager.config_path}")
    if config_manager.config_path.exists():
        print_success("File exists")
    else:
        print_warning("File does not exist (using defaults)")


async def cmd_auth(args) -> None:
    """Manage authentication."""

    config_manager = ConfigManager(args.config)

    if args.auth_action == 'init':
        # Initialize authentication
        # Use BearerAuthConfig defaults if not provided
        bearer_data = {}
        if args.issuer:
            bearer_data['issuer'] = args.issuer
        if args.audience:
            bearer_data['audience'] = args.audience
        if args.key_path:
            bearer_data['key_path'] = args.key_path
        bearer_config = BearerAuthConfig.model_validate(bearer_data)
        auth_config = AuthConfig.model_validate({'bearer': bearer_config})

        # Create bearer auth manager
        auth_manager = BearerAuthManager(auth_config.bearer)

        # Try to generate keys - this will fail if they exist
        try:
            auth_manager.generate_keys()
            print_success(
                f"Generated new RSA keypair for audience '{auth_config.bearer.audience}'\n"
                f"Private key: {auth_config.bearer.key_path}/{auth_config.bearer.audience}.key\n"
                f"SSH public key: {auth_config.bearer.key_path}/{auth_config.bearer.audience}.key.pub"
            )

            # Save auth config only if non-default
            default_config = BearerAuthConfig()
            if (auth_config.bearer.issuer != default_config.issuer or
                auth_config.bearer.audience != default_config.audience):
                if config_manager.save_auth_config(auth_config):
                    print_info(f"Auth config saved to: {config_manager.auth_config_path}")
                else:
                    print_error("Failed to save auth configuration")
                    sys.exit(1)

            print_success(f"Authentication initialized with audience '{auth_config.bearer.audience}'")
        except RuntimeError as e:
            print_error(str(e))
            sys.exit(1)

    elif args.auth_action == 'status':
        # Show auth status
        auth_config = config_manager.load_auth_config()
        if auth_config.bearer.private_key_exists:
            print_info(
                "Authentication is ENABLED (Bearer Token)\n"
                f"Issuer: {auth_config.bearer.issuer}\n"
                f"Audience: {auth_config.bearer.audience}\n"
                f"Key path: {auth_config.bearer.key_path}"
            )

            if auth_config.bearer.private_key_path.exists():
                print_success(f"Private key file: {auth_config.bearer.private_key_path}")
            if auth_config.bearer.private_key_env:
                print_info("Private key also available via MAGG_PRIVATE_KEY env var")

            if auth_config.bearer.public_key_exists:
                print_info(f"SSH public key exists: {auth_config.bearer.public_key_path}")

            if auth_config.bearer.private_key_env:
                print_info("Private key also available via MAGG_PRIVATE_KEY env var")
        else:
            print_info(
                "Authentication is DISABLED\n"
                "Run 'magg auth init' to enable authentication"
            )

    elif args.auth_action == 'token':
        auth_config = config_manager.load_auth_config()
        if not auth_config.bearer.private_key_exists:
            print_error("No authentication keys found. Run 'magg auth init' first")
            sys.exit(1)

        auth_manager = BearerAuthManager(auth_config.bearer)
        try:
            auth_manager.load_keys()
        except RuntimeError as e:
            print_error(str(e))
            print_info("Run 'magg auth init' to generate keys")
            sys.exit(1)

        token = auth_manager.create_token(subject=args.subject, hours=args.hours, scopes=args.scopes)
        if not token:
            print_error("Failed to generate token")
            sys.exit(1)

        if args.quiet:
            print(token)
        elif args.export:
            print(f"export MAGG_JWT={token}")
        else:
            print_success(f"Generated token for '{args.subject}' (valid for {args.hours} hours)")
            print_newline()
            print(token)

    elif args.auth_action == 'public-key':
        auth_config = config_manager.load_auth_config()
        if not auth_config.bearer.private_key_exists:
            print_error("No authentication keys found. Run 'magg auth init' first")
            sys.exit(1)

        auth_manager = BearerAuthManager(auth_config.bearer)
        try:
            auth_manager.load_keys()
        except RuntimeError as e:
            print_error(str(e))
            sys.exit(1)

        public_key = auth_manager.get_public_key()
        if public_key:
            print(public_key)
        else:
            print_error("Failed to get public key")
            sys.exit(1)

    elif args.auth_action == 'private-key':
        auth_config = config_manager.load_auth_config()
        if not auth_config.bearer.private_key_exists:
            print_error("No authentication keys found. Run 'magg auth init' first")
            sys.exit(1)

        # Create bearer auth manager and load keys
        auth_manager = BearerAuthManager(auth_config.bearer)
        try:
            auth_manager.load_keys()
        except RuntimeError as e:
            print_error(str(e))
            sys.exit(1)

        private_key = auth_manager.get_private_key()
        if private_key:
            if serialization is None:
                print_error("cryptography package not available")
                sys.exit(1)
            pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')

            if args.export:
                single_line = pem.replace('\n', '\\n')
                print(f"export MAGG_PRIVATE_KEY={single_line}")
            elif args.oneline:
                single_line = pem.replace('\n', '\\n')
                print(single_line)
            else:
                print(pem)
        else:
            print_error("Failed to get private key")
            sys.exit(1)

    else:
        print_error("No auth action specified")
        sys.exit(1)


def create_parser() -> argparse.ArgumentParser:
    """Create the command line parser."""
    parser = argparse.ArgumentParser(
        prog='magg',
        description='Magg - MCP Aggregator: Manage and aggregate MCP servers',
        epilog='Use "magg <command> --help" for more information about a command.'
    )

    parser.add_argument(
        '--version', '-V',
        action='version',
        version=f'%(prog)s {__version__}',
    )

    parser.add_argument(
        '--config',
        type=str,
        help='Path to config file (default: .magg/config.json in current directory)'
    )

    subparsers = parser.add_subparsers(dest='subcommand', help='Commands')

    # Serve command
    serve_parser = subparsers.add_parser(
        'serve',
        help='Start Magg server',
        description='Start the Magg server in either stdio mode (default) or HTTP mode'
    )
    cmd_serve_args(serve_parser)

    # Server command
    server_parser = subparsers.add_parser('server', help='Manage servers')
    server_subparsers = server_parser.add_subparsers(dest='server_action', help='Server actions', required=True)

    # Server list
    server_subparsers.add_parser('list', help='List configured servers')

    # Server add
    server_add = server_subparsers.add_parser('add', help='Add a new server')
    server_add.add_argument('name', help='Server name')
    server_add.add_argument('source', help='URL of the server package/repository')
    server_add.add_argument('--prefix', help='Tool prefix (defaults to None)')
    server_add.add_argument('--command', help='Command to run the server')
    server_add.add_argument('--uri', help='URI for HTTP servers')
    server_add.add_argument('--env', nargs='*', help='Environment variables (KEY=VALUE)')
    server_add.add_argument('--cwd', dest='cwd', help='Working directory')
    server_add.add_argument('--notes', help='Setup notes')

    # Server remove
    server_remove = server_subparsers.add_parser('remove', help='Remove a server')
    server_remove.add_argument('name', help='Server name')
    server_remove.add_argument('--force', '-f', action='store_true', help='Remove without confirmation')

    # Server enable
    server_enable = server_subparsers.add_parser('enable', help='Enable a server')
    server_enable.add_argument('name', help='Server name')

    # Server disable
    server_disable = server_subparsers.add_parser('disable', help='Disable a server')
    server_disable.add_argument('name', help='Server name')

    # Server info (new)
    server_info = server_subparsers.add_parser('info', help='Show detailed information about a server')
    server_info.add_argument('name', help='Server name')

    # Config command
    config_parser = subparsers.add_parser('config', help='Manage configuration')
    config_subparsers = config_parser.add_subparsers(dest='config_action', help='Config actions', required=True)

    # Config show (status)
    config_subparsers.add_parser('show', help='Show current configuration status')

    # Config export
    config_export = config_subparsers.add_parser('export', help='Export configuration')
    config_export.add_argument('--output', '-o', help='Output file (default: stdout)')

    # Config path
    config_subparsers.add_parser('path', help='Show configuration file path')

    # Backward compatibility - deprecated commands
    # Only add them if a deprecated command is actually being used
    deprecated_commands = ['add-server', 'list-servers', 'remove-server', 'enable-server', 'disable-server', 'status', 'export']
    if len(sys.argv) > 1 and sys.argv[1] in deprecated_commands:
        add_parser = subparsers.add_parser('add-server', help=argparse.SUPPRESS)
        add_parser.add_argument('name', help='Server name')
        add_parser.add_argument('source', help='URL of the server package/repository')
        add_parser.add_argument('--prefix', help='Tool prefix')
        add_parser.add_argument('--command', help='Command to run the server')
        add_parser.add_argument('--uri', help='URI for HTTP servers')
        add_parser.add_argument('--env', nargs='*', help='Environment variables (KEY=VALUE)')
        add_parser.add_argument('--cwd', dest='cwd', help='Working directory')
        add_parser.add_argument('--notes', help='Setup notes')

        subparsers.add_parser('list-servers', help=argparse.SUPPRESS)

        remove_parser = subparsers.add_parser('remove-server', help=argparse.SUPPRESS)
        remove_parser.add_argument('name', help='Server name')
        remove_parser.add_argument('--force', '-f', action='store_true', help='Remove without confirmation')

        enable_parser = subparsers.add_parser('enable-server', help=argparse.SUPPRESS)
        enable_parser.add_argument('name', help='Server name')

        disable_parser = subparsers.add_parser('disable-server', help=argparse.SUPPRESS)
        disable_parser.add_argument('name', help='Server name')

        subparsers.add_parser('status', help=argparse.SUPPRESS)
        export_parser = subparsers.add_parser('export', help=argparse.SUPPRESS)
        export_parser.add_argument('--output', '-o', help='Output file (default: stdout)')

    # Kit command
    kit_parser = subparsers.add_parser('kit', help='Manage kits')
    kit_subparsers = kit_parser.add_subparsers(dest='kit_action', help='Kit actions', required=True)

    # Kit list
    kit_subparsers.add_parser('list', help='List available kits')

    # Kit load
    kit_load = kit_subparsers.add_parser('load', help='Load a kit into configuration')
    kit_load.add_argument('name', help='Kit name to load')
    kit_load.add_argument('--enable', action='store_true', default=None, help='Force enable all servers after loading')
    kit_load.add_argument('--no-enable', dest='enable', action='store_false', help='Force disable all servers after loading')

    # Kit info
    kit_info = kit_subparsers.add_parser('info', help='Show information about a kit')
    kit_info.add_argument('name', help='Kit name')
    
    # Kit export
    kit_export = kit_subparsers.add_parser('export', help='Export servers as a kit')
    kit_export.add_argument('--name', help='Kit name (optional)')
    kit_export.add_argument('--description', help='Kit description (optional)')
    kit_export.add_argument('--author', help='Kit author (optional)')
    kit_export.add_argument('--version', help='Kit version (optional)')
    kit_export.add_argument('--kit', help='Export a specific loaded kit instead of current config')
    kit_export.add_argument('--output', '-o', help='Output file (default: stdout)')

    # Auth command
    auth_parser = subparsers.add_parser('auth', help='Manage authentication')
    auth_subparsers = auth_parser.add_subparsers(dest='auth_action', help='Auth actions', required=True)

    # Initialize auth
    auth_init = auth_subparsers.add_parser('init', help='Initialize authentication')
    auth_init.add_argument('--issuer', help='Token issuer identifier (default: https://magg.local)')
    auth_init.add_argument('--audience', help='Token audience, also used as key name (default: magg)')
    auth_init.add_argument('--key-path', type=Path, help='Path for authentication keys (default: ~/.ssh/magg)')

    # Show auth status
    auth_subparsers.add_parser('status', help='Show authentication status')

    # Show public key
    auth_subparsers.add_parser('public-key', help='Show public key in PEM format')

    # Show private key
    auth_private = auth_subparsers.add_parser('private-key', help='Show private key')
    private_output_group = auth_private.add_mutually_exclusive_group()
    private_output_group.add_argument('--export', '-e', action='store_true', help='Output in single-line format for env vars')
    private_output_group.add_argument('--oneline', action='store_true', help='Output in single-line format')

    # Generate test token
    auth_token = auth_subparsers.add_parser('token', help='Generate a test token')
    auth_token.add_argument('--subject', default='dev-user', help='Token subject (default: dev-user)')
    auth_token.add_argument('--hours', type=int, default=24, help='Token validity in hours (default: 24)')
    auth_token.add_argument('--scopes', nargs='*', help='Permission scopes (space-separated)')

    output_group = auth_token.add_mutually_exclusive_group()
    output_group.add_argument('--quiet', '-q', action='store_true', help='Only output the token')
    output_group.add_argument('--export', '-e', action='store_true', help='Output as export command for eval')


    return parser


async def _deprecated_redirect(old_cmd: str, new_cmd: str, func, args):
    """Helper to show deprecation warning and call the original function."""
    print_warning(f"'{old_cmd}' is deprecated. Please use 'magg {new_cmd}' instead.")
    return await func(args)


async def run():
    """Main entry point (async)."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        sys.exit(1)

    # Map commands to functions
    commands = {
        'serve': cmd_serve,
        'server': cmd_server,
        'config': cmd_config,
        'kit': cmd_kit,
        'auth': cmd_auth,
        # Deprecated commands - show warning and redirect
        'add-server': lambda a: _deprecated_redirect('add-server', 'server add', cmd_add_server, a),
        'list-servers': lambda a: _deprecated_redirect('list-servers', 'server list', cmd_list_servers, a),
        'remove-server': lambda a: _deprecated_redirect('remove-server', 'server remove', cmd_remove_server, a),
        'enable-server': lambda a: _deprecated_redirect('enable-server', 'server enable', cmd_enable_server, a),
        'disable-server': lambda a: _deprecated_redirect('disable-server', 'server disable', cmd_disable_server, a),
        'status': lambda a: _deprecated_redirect('status', 'config show', cmd_status, a),
        'export': lambda a: _deprecated_redirect('export', 'config export', cmd_export, a),
    }

    cmd_func = commands.get(args.subcommand)
    if cmd_func:
        await cmd_func(args)
    else:
        parser.print_help()
        sys.exit(1)


def main():
    """Run the CLI."""
    global logger

    process.setup()

    logger = logging.getLogger(__name__)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        if os.getenv('MAGG_DEBUG', '').lower() in {'1', 'true', 'yes'}:
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
