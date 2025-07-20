"""Main CLI interface for Magg - Simplified implementation."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from . import __version__, process
from .auth import BearerAuthManager
from .kit import KitManager
from .server.runner import MaggRunner
from .settings import ConfigManager, ServerConfig, BearerAuthConfig, AuthConfig, KitInfo
from .util.system import get_subprocess_environment
from .util.terminal import (
    print_success, print_error, print_warning, print_startup_banner,
    print_info, print_server_list, print_status_summary, confirm_action,
    print_text
)

process.setup(source=__name__)

logger: logging.Logger = logging.getLogger(__name__)


def output_json(data: dict, output_path: Path | None = None) -> None:
    """Output JSON data to file or stdout."""
    if output_path:
        try:
            with output_path.open('w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print_error(f"Failed to write to {output_path}: {e}")
            raise
    else:
        print(json.dumps(data, indent=2))


async def cmd_serve(args) -> int:
    """Start Magg server.
    """
    if (args.http or args.hybrid) and not args.no_banner:
        print_startup_banner()

    env = get_subprocess_environment(inherit=args.env_pass, provided=args.env_set)
    runner = MaggRunner(args.config, env=env)

    try:
        if args.hybrid:
            logger.info("Starting hybrid server (stdio + HTTP on %s:%s)", args.host, args.port)
            await runner.run_hybrid(host=args.host, port=args.port)
        elif args.http:
            logger.info("Starting HTTP server on %s:%s", args.host, args.port)
            await runner.run_http(host=args.host, port=args.port)
        else:
            logger.info("Starting stdio server")
            await runner.run_stdio()

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Server shutdown requested")

    except Exception as e:
        logger.error("Server encountered an error: %s", e)
        return 1

    return 0


def cmd_serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '--http',
        action='store_true',
        help='Run as HTTP server instead of stdio mode'
    )
    parser.add_argument(
        '--hybrid',
        action='store_true',
        help='Run in hybrid mode (both stdio and HTTP)'
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
    parser.add_argument(
        '--no-banner',
        action='store_true',
        help='Suppress startup banner'
    )


async def cmd_add_server(args) -> int:
    """Add a new MCP server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name in config.servers:
        logger.debug("Attempt to add duplicate server: %s", args.name)
        print_error(f"Server '{args.name}' already exists")
        return 1

    env = None
    if args.env:
        try:
            env = dict(arg.split('=', 1) for arg in args.env)
        except ValueError:
            print_error("Invalid environment variable format. Use KEY=VALUE")
            return 1

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
            prefix=args.prefix,
            command=command,
            args=command_args,
            uri=args.uri,
            env=env,
            cwd=args.cwd,
            notes=args.notes
        )
    except ValueError as e:
        print_error(f"Invalid server configuration: {e}")
        return 1

    config.add_server(server)

    if config_manager.save_config(config):
        info = f"Added server '{args.name}'\n  Source: {args.source}\n  Prefix: {server.prefix}"
        if server.command:
            cmd_str = server.command + (' ' + ' '.join(server.args) if server.args else '')
            info += f"\n  Command: {cmd_str}"
        if server.notes:
            info += f"\n  Notes: {server.notes}"
        print_success(info)
        return 0
    else:
        print_error("Failed to save configuration")
        return 1


async def cmd_list_servers(args) -> int:
    """List configured servers."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    print_server_list(config.servers)
    return 0


async def cmd_remove_server(args) -> int:
    """Remove a server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name not in config.servers:
        logger.warning("Attempt to remove non-existent server: %s", args.name)
        print_error(f"Server '{args.name}' not found")
        return 1

    server = config.servers[args.name]
    print_info(f"Server to remove: {args.name}")
    print_text(
        f"  Source: {server.source}\n"
        f"  Prefix: {server.prefix}"
    )

    if not args.force and not confirm_action("Are you sure you want to remove this server?"):
        logger.debug("User cancelled removal of server '%s'", args.name)
        print_info("Removal cancelled")
        return 0

    config.remove_server(args.name)

    if config_manager.save_config(config):
        logger.debug("Successfully removed server '%s'", args.name)
        print_success(f"Removed server '{args.name}'")
        return 0
    else:
        print_error("Failed to save configuration")
        return 1


async def cmd_enable_server(args) -> int:
    """Enable a server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name not in config.servers:
        print_error(f"Server '{args.name}' not found")
        return 1

    server = config.servers[args.name]
    if server.enabled:
        print_info(f"Server '{args.name}' is already enabled")
        return 0

    server.enabled = True

    if config_manager.save_config(config):
        print_success(f"Enabled server '{args.name}'")
        print_text("The server will be mounted on next startup")
        return 0
    else:
        print_error("Failed to save configuration")
        return 1


async def cmd_disable_server(args) -> int:
    """Disable a server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name not in config.servers:
        print_error(f"Server '{args.name}' not found")
        return 1

    server = config.servers[args.name]
    if not server.enabled:
        print_info(f"Server '{args.name}' is already disabled")
        return 0

    server.enabled = False

    if config_manager.save_config(config):
        print_success(f"Disabled server '{args.name}'")
        print_text("If Magg is running, the server will be automatically unmounted")
        return 0
    else:
        print_error("Failed to save configuration")
        return 1


async def cmd_status(args) -> int:
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
    return 0


async def cmd_export(args) -> int:
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

    output_json(export_data, args.output)
    return 0


async def cmd_kit(args) -> int:
    """Manage kits."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()
    kit_manager = KitManager(config_manager)

    discovered = kit_manager.discover_kits()

    match args.kit_action:
        case 'list':
            if not discovered:
                print_warning("No kits found in kit.d directories")
                print_info(f"Search paths: {', '.join(str(p) for p in kit_manager.kitd_paths)}")
                return 0

            print_info(f"Available kits ({len(discovered)}):")
            for kit_name, kit_path in discovered.items():
                kit_config = kit_manager.load_kit(kit_path)
                if kit_config and kit_config.description:
                    print_text(f"  • {kit_name}: {kit_config.description}")
                else:
                    print_text(f"  • {kit_name}")
            return 0

        case 'load' | 'info':
            if args.name not in discovered:
                print_error(f"Kit '{args.name}' not found")
                print_info(f"Available kits: {', '.join(discovered.keys())}")
                return 1

            kit_path = discovered[args.name]
            kit_config = kit_manager.load_kit(kit_path)
            if not kit_config:
                print_error(f"Failed to load kit '{args.name}'")
                return 1

            if args.kit_action == 'info':
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
                    print_text("Links:")
                    for key, url in kit_config.links.items():
                        print_text(f"  • {key}: {url}")

                if kit_config.servers:
                    print_text(f"\nServers ({len(kit_config.servers)}):")
                    for server_name, server in kit_config.servers.items():
                        prefix_info = f" (prefix: {server.prefix})" if server.prefix else ""
                        print_text(f"  • {server_name}{prefix_info}")
                        if server.notes:
                            print_text(f"    {server.notes}")
                else:
                    print_text("\nNo servers in this kit")
                return 0

            else:  # load
                if args.name not in config.kits:
                    config.kits[args.name] = KitInfo(
                        name=args.name,
                        description=kit_config.description,
                        path=str(kit_path),
                        source="file"
                    )

                added_servers = []
                skipped_servers = []
                for server_name, server_config in kit_config.servers.items():
                    if server_name in config.servers:
                        skipped_servers.append(server_name)
                        continue

                    if args.enable is not None:
                        server_config.enabled = args.enable

                    server_config.kits = [args.name]

                    config.servers[server_name] = server_config
                    added_servers.append(server_name)

                if config_manager.save_config(config):
                    if added_servers:
                        print_success(f"Added {len(added_servers)} servers from kit '{args.name}':")
                        for name in added_servers:
                            status = "enabled" if config.servers[name].enabled else "disabled"
                            print_text(f"  • {name} ({status})")
                    if skipped_servers:
                        print_warning(f"Skipped {len(skipped_servers)} servers already in configuration:")
                        for name in skipped_servers:
                            print_text(f"  • {name}")
                    if not added_servers and not skipped_servers:
                        print_warning(f"Kit '{args.name}' contains no servers")
                else:
                    print_error("Failed to save configuration")
                    return 1
            return 0

        case 'export':
            if args.kit:
                if args.kit not in config.kits:
                    print_error(f"Kit '{args.kit}' is not loaded")
                    return 1

                kit_manager.load_kits_from_config(config)
                servers_to_export = kit_manager.get_kit_servers(args.kit)

                kit_info = config.kits[args.kit]
                export_name = args.name or kit_info.name
                export_description = args.description or kit_info.description or ""
            else:
                servers_to_export = config.servers
                export_name = args.name or "exported"
                export_description = args.description or "Exported from current configuration"

            kit_data = {
                "name": export_name,
                "description": export_description,
                "servers": {}
            }

            if args.author:
                kit_data["author"] = args.author
            if args.version:
                kit_data["version"] = args.version

            for name, server in servers_to_export.items():
                server_data = server.model_dump(
                    mode="json",
                    exclude_none=True, exclude_unset=True, exclude_defaults=True,
                    by_alias=True,
                    exclude={'name', 'kits'}
                )
                kit_data["servers"][name] = server_data

            output_json(kit_data, args.output)
            return 0

        case _:
            print_error(f"Unknown kit action: {args.kit_action}")
            return 1


async def cmd_server(args) -> int:
    """Manage servers."""
    if args.server_action == 'list':
        return await cmd_list_servers(args)
    elif args.server_action == 'add':
        return await cmd_add_server(args)
    elif args.server_action == 'remove':
        return await cmd_remove_server(args)
    elif args.server_action == 'enable':
        return await cmd_enable_server(args)
    elif args.server_action == 'disable':
        return await cmd_disable_server(args)
    elif args.server_action == 'info':
        return await cmd_server_info(args)
    else:
        print_error(f"Unknown server action: {args.server_action}")
        return 1


async def cmd_server_info(args) -> int:
    """Show detailed information about a server."""
    config_manager = ConfigManager(args.config)
    config = config_manager.load_config()

    if args.name not in config.servers:
        print_error(f"Server '{args.name}' not found")
        return 1

    server = config.servers[args.name]

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
        print_text("Environment Variables:")
        for key, value in server.env.items():
            print_text(f"  {key}={value}")

    if server.transport:
        print_text("Transport Configuration:")
        print_text(f"  {json.dumps(server.transport, indent=2)}")

    if server.notes:
        print_text(f"\nNotes: {server.notes}")

    if server.kits:
        print_text(f"\nIncluded in kits: {', '.join(server.kits)}")

    return 0


async def cmd_config(args) -> int:
    """Manage configuration."""
    if args.config_action == 'show':
        return await cmd_status(args)
    elif args.config_action == 'export':
        return await cmd_export(args)
    elif args.config_action == 'path':
        return await cmd_config_path(args)
    return 1


async def cmd_config_path(args) -> int:
    """Show configuration file path."""
    config_manager = ConfigManager(args.config)
    print(config_manager.config_path)
    return 0


async def cmd_auth(args) -> int:
    """Manage authentication."""
    config_manager = ConfigManager(args.config)

    match args.auth_action:
        case 'init':
            bearer_data = {}
            if args.issuer:
                bearer_data['issuer'] = args.issuer
            if args.audience:
                bearer_data['audience'] = args.audience
            if args.key_path:
                bearer_data['key_path'] = args.key_path
            bearer_config = BearerAuthConfig.model_validate(bearer_data)
            auth_config = AuthConfig.model_validate({'bearer': bearer_config})

            auth_manager = BearerAuthManager(auth_config.bearer)

            auth_manager.generate_keys()
            print_success(f"Generated new RSA keypair for audience '{auth_config.bearer.audience}'")
            print_text(
                f"Private key: {auth_config.bearer.key_path}/{auth_config.bearer.audience}.key\n"
                f"SSH public key: {auth_config.bearer.key_path}/{auth_config.bearer.audience}.key.pub"
            )

            default_config = BearerAuthConfig()
            if (auth_config.bearer.issuer != default_config.issuer or
                auth_config.bearer.audience != default_config.audience):
                if config_manager.save_auth_config(auth_config):
                    print_info(f"Auth config saved to: {config_manager.auth_config_path}")
                else:
                    print_error("Failed to save auth configuration")
                    return 1

            print_success(f"Authentication initialized with audience '{auth_config.bearer.audience}'")
            return 0

        case 'status':
            auth_config = config_manager.load_auth_config()
            if auth_config.bearer.private_key_exists:
                print_info("Authentication is ENABLED (Bearer Token)")
                print_text(
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
                print_info("Authentication is DISABLED")
                print_text("Run 'magg auth init' to enable authentication")
            return 0

        case 'token':
            auth_config = config_manager.load_auth_config()
            if not auth_config.bearer.private_key_exists:
                print_error("No authentication keys found. Run 'magg auth init' first")
                return 1

            auth_manager = BearerAuthManager(auth_config.bearer)
            try:
                auth_manager.load_keys()
            except RuntimeError as e:
                print_error(str(e))
                print_info("Run 'magg auth init' to generate keys")
                return 1

            token = auth_manager.create_token(subject=args.subject, hours=args.hours, scopes=args.scopes)
            if not token:
                print_error("Failed to generate token")
                return 1

            if args.quiet:
                print(token)
            elif args.export:
                print(f"export MAGG_JWT={token}")
            else:
                print_success(f"Generated token for '{args.subject}' (valid for {args.hours} hours)")
                print_text()
                print_text(token)
            return 0

        case 'public-key' | 'private-key':
            auth_config = config_manager.load_auth_config()
            if not auth_config.bearer.private_key_exists:
                print_error("No authentication keys found. Run 'magg auth init' first")
                return 1

            auth_manager = BearerAuthManager(auth_config.bearer)
            try:
                auth_manager.load_keys()
            except RuntimeError as e:
                print_error(str(e))
                return 1

            if args.auth_action == 'public-key':
                public_key = auth_manager.get_public_key()
                if public_key:
                    print(public_key)
                else:
                    print_error("Failed to get public key")
                    return 1
            else:
                private_key = auth_manager.get_private_key()
                if private_key:
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
                    return 1
            return 0

        case _:
            print_error("No auth action specified")
            return 1


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

    parser.add_argument(
        '-e', '--env-pass',
        action='store_true',
        help='Pass environment to stdio MCP servers'
    )

    parser.add_argument(
        '-E', '--env-set',
        nargs=2,
        action='append',
        metavar=('KEY', 'VALUE'),
        help='Set environment variable for stdio MCP servers (can be used multiple times)'
    )

    subparsers = parser.add_subparsers(dest='subcommand', help='Commands')

    serve_parser = subparsers.add_parser(
        'serve',
        help='Start Magg server',
        description='Start the Magg server in either stdio mode (default) or HTTP mode'
    )
    cmd_serve_args(serve_parser)

    server_parser = subparsers.add_parser('server', help='Manage servers')
    server_subparsers = server_parser.add_subparsers(dest='server_action', help='Server actions', required=True)

    server_subparsers.add_parser('list', help='List configured servers')

    server_add = server_subparsers.add_parser('add', help='Add a new server')
    server_add.add_argument('name', help='Server name')
    server_add.add_argument('source', help='URL of the server package/repository')
    server_add.add_argument('--prefix', help='Tool prefix (defaults to None)')
    server_add.add_argument('--command', help='Command to run the server')
    server_add.add_argument('--uri', help='URI for HTTP servers')
    server_add.add_argument('--env', nargs='*', help='Environment variables (KEY=VALUE)')
    server_add.add_argument('--cwd', dest='cwd', help='Working directory')
    server_add.add_argument('--notes', help='Setup notes')

    server_remove = server_subparsers.add_parser('remove', help='Remove a server')
    server_remove.add_argument('name', help='Server name')
    server_remove.add_argument('--force', '-f', action='store_true', help='Remove without confirmation')

    server_enable = server_subparsers.add_parser('enable', help='Enable a server')
    server_enable.add_argument('name', help='Server name')

    server_disable = server_subparsers.add_parser('disable', help='Disable a server')
    server_disable.add_argument('name', help='Server name')

    server_info = server_subparsers.add_parser('info', help='Show detailed information about a server')
    server_info.add_argument('name', help='Server name')

    config_parser = subparsers.add_parser('config', help='Manage configuration')
    config_subparsers = config_parser.add_subparsers(dest='config_action', help='Config actions', required=True)

    config_subparsers.add_parser('show', help='Show current configuration status')

    config_export = config_subparsers.add_parser('export', help='Export configuration')
    config_export.add_argument('--output', '-o', type=Path, help='Output file (default: stdout)')

    config_subparsers.add_parser('path', help='Show configuration file path')

    kit_parser = subparsers.add_parser('kit', help='Manage kits')
    kit_subparsers = kit_parser.add_subparsers(dest='kit_action', help='Kit actions', required=True)

    kit_subparsers.add_parser('list', help='List available kits')

    kit_load = kit_subparsers.add_parser('load', help='Load a kit into configuration')
    kit_load.add_argument('name', help='Kit name to load')
    kit_load.add_argument('--enable', action='store_true', default=None, help='Force enable all servers after loading')
    kit_load.add_argument('--no-enable', dest='enable', action='store_false', help='Force disable all servers after loading')

    kit_info = kit_subparsers.add_parser('info', help='Show information about a kit')
    kit_info.add_argument('name', help='Kit name')

    kit_export = kit_subparsers.add_parser('export', help='Export servers as a kit')
    kit_export.add_argument('--name', help='Kit name (optional)')
    kit_export.add_argument('--description', help='Kit description (optional)')
    kit_export.add_argument('--author', help='Kit author (optional)')
    kit_export.add_argument('--version', help='Kit version (optional)')
    kit_export.add_argument('--kit', help='Export a specific loaded kit instead of current config')
    kit_export.add_argument('--output', '-o', type=Path, help='Output file (default: stdout)')

    auth_parser = subparsers.add_parser('auth', help='Manage authentication')
    auth_subparsers = auth_parser.add_subparsers(dest='auth_action', help='Auth actions', required=True)

    auth_init = auth_subparsers.add_parser('init', help='Initialize authentication')
    auth_init.add_argument('--issuer', help='Token issuer identifier (default: https://magg.local)')
    auth_init.add_argument('--audience', help='Token audience, also used as key name (default: magg)')
    auth_init.add_argument('--key-path', type=Path, help='Path for authentication keys (default: ~/.ssh/magg)')

    auth_subparsers.add_parser('status', help='Show authentication status')

    auth_subparsers.add_parser('public-key', help='Show public key in PEM format')

    auth_private = auth_subparsers.add_parser('private-key', help='Show private key')
    private_output_group = auth_private.add_mutually_exclusive_group()
    private_output_group.add_argument('--export', '-e', action='store_true', help='Output in single-line format for env vars')
    private_output_group.add_argument('--oneline', action='store_true', help='Output in single-line format')

    auth_token = auth_subparsers.add_parser('token', help='Generate a test token')
    auth_token.add_argument('--subject', default='dev-user', help='Token subject (default: dev-user)')
    auth_token.add_argument('--hours', type=int, default=24, help='Token validity in hours (default: 24)')
    auth_token.add_argument('--scopes', nargs='*', help='Permission scopes (space-separated)')

    output_group = auth_token.add_mutually_exclusive_group()
    output_group.add_argument('--quiet', '-q', action='store_true', help='Only output the token')
    output_group.add_argument('--export', '-e', action='store_true', help='Output as export command for eval')

    return parser


async def run():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        exit(1)

    commands = {
        'serve': cmd_serve,
        'server': cmd_server,
        'config': cmd_config,
        'kit': cmd_kit,
        'auth': cmd_auth,
    }

    cmd_func = commands.get(args.subcommand)

    if cmd_func:
        if exit_code := await cmd_func(args):
            exit(exit_code)

    else:
        parser.print_help()
        exit(1)


def main():
    """Run the CLI.
    """
    process.setup()
    asyncio.run(run())


if __name__ == '__main__':
    main()
