"""Utilities for patching stdio transports to control stderr behavior."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

__all__ = "patch_stdio_transport_stderr",


def patch_stdio_transport_stderr(transport):
    """Patch a stdio transport to suppress stderr output.

    This monkey-patches the transport's connect method to redirect stderr to /dev/null.
    Only works for StdioTransport and its subclasses.
    """
    from fastmcp.client.transports import StdioTransport

    if not isinstance(transport, StdioTransport):
        return transport

    original_connect = transport.connect

    async def patched_connect(**session_kwargs):
        from mcp.client import stdio
        original_stdio_client = stdio.stdio_client

        @asynccontextmanager
        async def silent_stdio_client(server_params, errlog=None):
            with Path(os.devnull).open('w') as devnull:
                async with original_stdio_client(server_params, errlog=devnull) as result:
                    yield result

        stdio.stdio_client = silent_stdio_client

        try:
            return await original_connect(**session_kwargs)

        finally:
            stdio.stdio_client = original_stdio_client

    transport.connect = patched_connect
    return transport
