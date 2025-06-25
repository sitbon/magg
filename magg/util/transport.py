"""Transport utilities for Magg - handles FastMCP transport selection and configuration.
"""
import sys
from pathlib import Path
from typing import Any
from fastmcp.client.transports import (
    infer_transport,
    StdioTransport,
    NpxStdioTransport,
    UvxStdioTransport,
    FastMCPStdioTransport,
    SSETransport,
    StreamableHttpTransport,
    ClientTransport
)
from .transports import NoValidatePythonStdioTransport, NoValidateNodeStdioTransport

__all__ = "get_transport_for_command", "get_transport_for_uri", "TRANSPORT_DOCS"


def get_transport_for_command(
    command: str,
    args: list[str],
    env: dict[str, str] | None = None,
    working_dir: Path | None = None,
    transport_config: dict[str, Any] | None = None
) -> ClientTransport:
    """
    Create appropriate transport based on command and configuration.

    Args:
        command: Main command (e.g., "python", "node", "uvx", "npx")
        args: Command arguments
        env: Environment variables
        working_dir: Working directory
        transport_config: Transport-specific configuration

    Returns:
        Configured ClientTransport instance
    """
    transport_config = transport_config or {}

    # Handle special commands with specific transport classes
    if command == "python":
        # Python execution - use our custom transport that doesn't validate paths
        # This handles python script.py, python -m module, etc.
        if args:
            return NoValidatePythonStdioTransport(
                script_path=args[0],  # Could be script path, -m, or other Python arg
                args=args[1:] if len(args) > 1 else None,
                env=env,
                cwd=str(working_dir) if working_dir else None,
                python_cmd=transport_config.get("python_cmd", sys.executable),
                keep_alive=transport_config.get("keep_alive", True)
            )

    elif command == "node":
        # Node.js execution - use our custom transport that doesn't validate paths
        if args:
            return NoValidateNodeStdioTransport(
                script_path=args[0],  # Could be script path or other Node arg
                args=args[1:],
                env=env,
                cwd=str(working_dir) if working_dir else None,
                node_cmd=transport_config.get("node_cmd", "node"),
                keep_alive=transport_config.get("keep_alive", True)
            )

    elif command == "npx":
        # NPX package execution
        if args:
            return NpxStdioTransport(
                package=args[0],
                args=args[1:],
                project_directory=str(working_dir) if working_dir else None,
                env_vars=env,
                use_package_lock=transport_config.get("use_package_lock", True),
                keep_alive=transport_config.get("keep_alive", True)
            )

    elif command == "uvx":
        # UVX tool execution
        if args:
            return UvxStdioTransport(
                tool_name=args[0],
                tool_args=args[1:],
                project_directory=str(working_dir) if working_dir else None,
                python_version=transport_config.get("python_version"),
                with_packages=transport_config.get("with_packages"),
                from_package=transport_config.get("from_package"),
                env_vars=env,
                keep_alive=transport_config.get("keep_alive", True)
            )

    elif command == "fastmcp":
        # FastMCP server execution
        if args and args[0] == "run":
            # Extract script path from fastmcp run command
            script_idx = args.index("run") + 1 if "run" in args else 1
            if script_idx < len(args):
                return FastMCPStdioTransport(
                    script_path=args[script_idx],
                    args=args[script_idx + 1:],
                    env=env,
                    cwd=str(working_dir) if working_dir else None,
                    keep_alive=transport_config.get("keep_alive", True)
                )

    # Default to generic StdioTransport for other commands
    return StdioTransport(
        command=command,
        args=args,
        env=env,
        cwd=str(working_dir) if working_dir else None,
        keep_alive=transport_config.get("keep_alive", True)
    )


def get_transport_for_uri(
    uri: str,
    transport_config: dict[str, Any] | None = None
) -> ClientTransport:
    """
    Create appropriate transport for URI-based servers.

    Args:
        uri: Server URI
        transport_config: Transport-specific configuration

    Returns:
        Configured ClientTransport instance
    """
    transport_config = transport_config or {}

    # Check if it's an SSE endpoint
    if uri.endswith("/sse") or uri.endswith("/sse/"):
        return SSETransport(
            url=uri,
            headers=transport_config.get("headers"),
            auth=transport_config.get("auth"),
            sse_read_timeout=transport_config.get("sse_read_timeout"),
            httpx_client_factory=transport_config.get("httpx_client_factory")
        )

    # Default to StreamableHttpTransport for HTTP/HTTPS
    if uri.startswith(("http://", "https://")):
        return StreamableHttpTransport(
            url=uri,
            headers=transport_config.get("headers"),
            auth=transport_config.get("auth"),
            sse_read_timeout=transport_config.get("sse_read_timeout"),
            httpx_client_factory=transport_config.get("httpx_client_factory")
        )

    # Fall back to infer_transport for other cases
    return infer_transport(uri)


# Transport documentation for tool descriptions
TRANSPORT_DOCS = """
Common options for all command-based servers:
- `keep_alive` (boolean): Keep the process alive between requests (default: true)

Python servers (command="python"):
- `python_cmd` (string): Python executable path (default: sys.executable)

Node.js servers (command="node"):
- `node_cmd` (string): Node executable path (default: "node")

NPX servers (command="npx"):
- `use_package_lock` (boolean): Use package-lock.json if present (default: true)

UVX servers (command="uvx"):
- `python_version` (string): Python version to use (e.g., "3.13")
- `with_packages` (array): Additional packages to install
- `from_package` (string): Install tool from specific package

HTTP/SSE servers (uri-based):
- `headers` (object): HTTP headers to include
- `auth` (string): Authentication method ("oauth" or bearer token)
- `sse_read_timeout` (number): Timeout for SSE reads in seconds

Examples:
- Python: `{"keep_alive": false, "python_cmd": "/usr/bin/python3"}`
- UVX: `{"python_version": "3.11", "with_packages": ["requests", "pandas"]}`
- HTTP: `{"headers": {"Authorization": "Bearer token123"}, "sse_read_timeout": 30}`
"""
