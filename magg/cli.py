#!/usr/bin/env python3
"""Main CLI interface for Magg - Simplified implementation."""

import argparse
import asyncio
import json
import os
import sys
import logging
from pathlib import Path

from . import __version__, process
from .settings import ConfigManager, ServerConfig, AuthConfig, BearerAuthConfig
from .util.terminal import (
    print_success, print_error, print_warning, print_startup_banner,
    print_info, print_server_list, print_status_summary, confirm_action,
    print_newline
)


process.setup(source=__name__)

logger: logging.Logger | None = logging.getLogger(__name__)


async def cmd_serve(args) -> None:
    """Start Magg server."""
    from magg.server.runner import MaggRunner

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
            working_dir=args.working_dir,
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
    print_info(f"Server to remove: {args.name}")
    print(f"  Source: {server.source}")
    print(f"  Prefix: {server.prefix}")

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
        print_success(f"Enabled server '{args.name}'")
        print_info("The server will be mounted on next startup")
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
        print_success(f"Disabled server '{args.name}'")
        print_warning("The server will remain mounted until Magg is restarted")
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


async def cmd_auth(args) -> None:
    """Manage authentication."""
    from .auth import BearerAuthManager
    from .settings import AuthConfig

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
            print_success(f"Generated new RSA keypair for audience '{auth_config.bearer.audience}'")
            print_info(f"Private key: {auth_config.bearer.key_path}/{auth_config.bearer.audience}.key")
            print_info(f"SSH public key: {auth_config.bearer.key_path}/{auth_config.bearer.audience}.key.pub")

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
            print_info("Authentication is ENABLED (Bearer Token)")
            print_info(f"Issuer: {auth_config.bearer.issuer}")
            print_info(f"Audience: {auth_config.bearer.audience}")
            print_info(f"Key path: {auth_config.bearer.key_path}")

            if auth_config.bearer.private_key_path.exists():
                print_success(f"Private key file: {auth_config.bearer.private_key_path}")
            if auth_config.bearer.private_key_env:
                print_info("Private key also available via MAGG_PRIVATE_KEY env var")

            if auth_config.bearer.public_key_exists:
                print_info(f"SSH public key exists: {auth_config.bearer.public_key_path}")

            if auth_config.bearer.private_key_env:
                print_info("Private key also available via MAGG_PRIVATE_KEY env var")
        else:
            print_info("Authentication is DISABLED")
            print_info("Run 'magg auth init' to enable authentication")

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
            from cryptography.hazmat.primitives import serialization
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

    # Add server command
    add_parser = subparsers.add_parser('add-server', help='Add a new server')
    add_parser.add_argument('name', help='Server name')
    add_parser.add_argument('source', help='URL of the server package/repository')
    add_parser.add_argument('--prefix', help='Tool prefix (defaults to server name)')
    add_parser.add_argument('--command', help='Command to run the server')
    add_parser.add_argument('--uri', help='URI for HTTP servers')
    add_parser.add_argument('--env', nargs='*', help='Environment variables (KEY=VALUE)')
    add_parser.add_argument('--working-dir', help='Working directory')
    add_parser.add_argument('--notes', help='Setup notes')

    # List servers
    subparsers.add_parser('list-servers', help='List configured servers')

    # Remove server
    remove_parser = subparsers.add_parser('remove-server', help='Remove a server')
    remove_parser.add_argument('name', help='Server name')
    remove_parser.add_argument('--force', '-f', action='store_true', help='Remove without confirmation')

    # Enable/disable server
    enable_parser = subparsers.add_parser('enable-server', help='Enable a server')
    enable_parser.add_argument('name', help='Server name')

    disable_parser = subparsers.add_parser('disable-server', help='Disable a server')
    disable_parser.add_argument('name', help='Server name')

    # Status command
    subparsers.add_parser('status', help='Show Magg status')

    # Export command
    export_parser = subparsers.add_parser('export', help='Export configuration')
    export_parser.add_argument('--output', '-o', help='Output file (default: stdout)')

    # Auth command
    auth_parser = subparsers.add_parser('auth', help='Manage authentication')
    auth_subparsers = auth_parser.add_subparsers(dest='auth_action', help='Auth actions')

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
        'add-server': cmd_add_server,
        'list-servers': cmd_list_servers,
        'remove-server': cmd_remove_server,
        'enable-server': cmd_enable_server,
        'disable-server': cmd_disable_server,
        'status': cmd_status,
        'export': cmd_export,
        'auth': cmd_auth,
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
        if os.getenv('MAGG_DEBUG').lower() in {'1', 'true', 'yes'}:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
