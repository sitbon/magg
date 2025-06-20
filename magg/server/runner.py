"""Server runner utilities for MAGG with proper signal handling.
"""
import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

from magg.server import MAGGServer

logger = logging.getLogger(__name__)


class ServerRunner:
    """Manages MAGG server lifecycle with proper signal handling."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.server: Optional[MAGGServer] = None
        self.shutdown_event = asyncio.Event()
        self._original_sigint = None
        self._original_sigterm = None

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signame = signal.Signals(signum).name
        print(f"\n\nReceived {signame}, shutting down gracefully...", file=sys.stderr)
        print("Please wait for cleanup to complete.", file=sys.stderr)
        self.shutdown_event.set()

        # Prevent multiple signal handlers from firing
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        # Store original handlers
        self._original_sigint = signal.signal(signal.SIGINT, self._handle_signal)
        self._original_sigterm = signal.signal(signal.SIGTERM, self._handle_signal)

    def _restore_signal_handlers(self):
        """Restore original signal handlers."""
        if self._original_sigint:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm:
            signal.signal(signal.SIGTERM, self._original_sigterm)

    @asynccontextmanager
    async def server_context(self):
        """Context manager for server lifecycle."""
        try:
            # Create and setup server
            self.server = MAGGServer(self.config_path)
            await self.server.setup()
            yield self.server
        finally:
            # Cleanup
            if self.server:
                # Any cleanup needed
                pass

    async def run_stdio(self):
        """Run server in stdio mode with proper signal handling."""
        self._setup_signal_handlers()

        try:
            async with self.server_context() as server:
                print("MAGG server started in stdio mode", file=sys.stderr)
                print("Ready for MCP client connections...", file=sys.stderr)
                print("Press Ctrl+C to stop gracefully", file=sys.stderr)

                # Create task for the server
                server_task = asyncio.create_task(server.run_stdio())
                shutdown_task = asyncio.create_task(self.shutdown_event.wait())

                # Wait for either completion or shutdown
                done, pending = await asyncio.wait(
                    [server_task, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check if server task had an error
                for task in done:
                    if task is server_task and task.exception():
                        logger.error("Server task failed with exception: %s", task.exception())
                        raise task.exception()

        finally:
            self._restore_signal_handlers()
            logger.debug("MAGG server stopped")
            # print("\nMAGG server stopped.", file=sys.stderr)

    async def run_http(self, host: str = "localhost", port: int = 8000):
        """Run server in HTTP mode with proper signal handling."""
        self._setup_signal_handlers()

        try:
            async with self.server_context() as server:
                logger.debug("Starting MAGG HTTP server on %s:%s", host, port)
                # print(f"Starting MAGG HTTP server on {host}:{port}", file=sys.stderr)
                # print(f"Server URL: http://{host}:{port}/", file=sys.stderr)
                # print("Press Ctrl+C to stop gracefully", file=sys.stderr)
                # print("-" * 50, file=sys.stderr)

                # Create task for the server
                server_task = asyncio.create_task(server.run_http(host, port))
                shutdown_task = asyncio.create_task(self.shutdown_event.wait())

                # Wait for either completion or shutdown
                done, pending = await asyncio.wait(
                    [server_task, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check if server task had an error
                for task in done:
                    if task is server_task and task.exception():
                        logger.error("HTTP server task failed with exception: %s", task.exception())
                        raise task.exception()

        finally:
            self._restore_signal_handlers()
            logger.debug("MAGG HTTP server stopped")
            # print("\nMAGG HTTP server stopped.", file=sys.stderr)


def print_startup_banner():
    """Print a nice startup banner."""
    banner = """
╔═══════════════════════════════════════════════════╗
║                                                   ║
║        ███╗   ███╗ █████╗  ██████╗  ██████╗       ║
║        ████╗ ████║██╔══██╗██╔════╝ ██╔════╝       ║
║        ██╔████╔██║███████║██║  ███╗██║  ███╗      ║
║        ██║╚██╔╝██║██╔══██║██║   ██║██║   ██║      ║
║        ██║ ╚═╝ ██║██║  ██║╚██████╔╝╚██████╔╝      ║
║        ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝       ║
║                                                   ║
║          MCP Aggregator - Tool Ecosystem          ║
║   Organizing and Managing Your MCP Environment    ║
╚═══════════════════════════════════════════════════╝
"""
    if not os.environ.get("MAGG_QUIET", "").lower() in ("1", "true", "yes"):
        if os.environ.get("NO_RICH", "").lower() in ("1", "true", "yes"):
            print(banner, file=sys.stderr)
        else:
            try:
                from rich.console import Console
                console = Console(file=sys.stderr, width=80)
                # style the banner with rich
                console.print(banner, style="bold cyan purple italic")
            except ImportError:
                print(banner, file=sys.stderr)
