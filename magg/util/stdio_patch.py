"""Utilities for patching stdio transports to control stderr behavior."""
import os
from contextlib import asynccontextmanager


def patch_stdio_transport_stderr(transport):
    """Patch a stdio transport to suppress stderr output.

    This monkey-patches the transport's connect method to redirect stderr to /dev/null.
    Only works for StdioTransport and its subclasses.
    """
    from fastmcp.client.transports import StdioTransport

    if not isinstance(transport, StdioTransport):
        return transport

    # Save the original connect method
    original_connect = transport.connect

    async def patched_connect(**session_kwargs):
        # Monkey-patch stdio_client to suppress stderr
        from mcp.client import stdio
        original_stdio_client = stdio.stdio_client

        # Create a wrapper that redirects stderr to devnull
        @asynccontextmanager
        async def silent_stdio_client(server_params, errlog=None):
            # Open devnull for stderr
            with open(os.devnull, 'w') as devnull:
                async with original_stdio_client(server_params, errlog=devnull) as result:
                    yield result

        # Apply the patch
        stdio.stdio_client = silent_stdio_client
        try:
            # Call the original connect
            result = await original_connect(**session_kwargs)
            return result
        finally:
            # Restore the original function
            stdio.stdio_client = original_stdio_client

    # Replace the connect method
    transport.connect = patched_connect
    return transport
