"""Server runner utilities for Magg with proper signal handling.
"""
import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from functools import cached_property
from typing import Callable, Coroutine

from fastmcp import Client
from fastmcp.client import FastMCPTransport

from .server import MaggServer

logger = logging.getLogger(__name__)


class MaggRunner:
    """Manages Magg server lifecycle with proper signal handling."""
    _server: MaggServer
    _shutdown_event: asyncio.Event
    _original_sigint: Callable | None
    _original_sigterm: Callable | None
    _hook_signals: bool
    _hooked_signals: bool = False

    def __init__(self, config_path: str | None = None, *, hook_signals: bool = True):
        self._server = MaggServer(config_path)
        self._shutdown_event = asyncio.Event()
        self._original_sigint = None
        self._original_sigterm = None
        self._hook_signals = hook_signals

    @cached_property
    def client(self) -> Client:
        """Create an in-memory client connected to the Magg server. [cached]"""
        return Client(FastMCPTransport(self._server.mcp))

    @property
    def server(self) -> MaggServer:
        """Get the current Magg server instance."""
        return self._server

    async def __aenter__(self):
        """Enter the server context manager."""
        await self._server.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Exit the server context manager."""
        await self._server.__aexit__(exc_type, exc_value, traceback)

    # noinspection PyUnusedLocal
    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signame = signal.Signals(signum).name
        logger.info("Received signal %s, shutting down gracefully...", signame)
        self._shutdown_event.set()

        # Prevent multiple signal handlers from firing
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        if self._hook_signals and self._hooked_signals is False:
            self._original_sigint = signal.signal(signal.SIGINT, self._handle_signal)
            self._original_sigterm = signal.signal(signal.SIGTERM, self._handle_signal)
            self._hooked_signals = True

    def _restore_signal_handlers(self):
        """Restore original signal handlers."""
        if self._hook_signals and self._hooked_signals:
            if self._original_sigint:
                signal.signal(signal.SIGINT, self._original_sigint)
            if self._original_sigterm:
                signal.signal(signal.SIGTERM, self._original_sigterm)
            self._hooked_signals = False

    @asynccontextmanager
    async def _server_context(self):
        """Context manager for server lifecycle."""
        self._setup_signal_handlers()

        try:
            async with self:
                yield self._server
        finally:
            self._restore_signal_handlers()

    async def _serve(self, coro: Coroutine):
        server_task = asyncio.create_task(coro)
        shutdown_task = asyncio.create_task(self._shutdown_event.wait())

        done, pending = await asyncio.wait(
            [server_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        for task in done:
            if task is server_task and task.exception():
                logger.error("Server task failed with exception: %s", task.exception())
                raise task.exception()

    async def run_stdio(self):
        """Run server in stdio mode with proper signal handling."""
        try:
            async with self._server_context() as server:
                logger.debug("Starting Magg server in stdio mode")
                await self._serve(server.run_stdio())

        finally:
            logger.debug("Magg server stopped")

    async def run_http(self, host: str = "localhost", port: int = 8000):
        """Run server in HTTP mode with proper signal handling."""
        try:
            async with self._server_context() as server:
                logger.debug("Starting Magg HTTP server on %s:%s", host, port)
                await self._serve(server.run_http(host, port))

        finally:
            logger.debug("Magg HTTP server stopped")

    async def start_stdio(self) -> asyncio.Task:
        """Start the server in stdio mode in a different task."""
        return asyncio.create_task(self.run_stdio())

    async def start_http(self, host: str = "localhost", port: int = 8000) -> asyncio.Task:
        """Start the server in HTTP mode in a different task."""
        return asyncio.create_task(self.run_http(host, port))
