"""Server runner utilities for MAGG with proper signal handling.
"""
import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from functools import cached_property
from typing import Callable, Coroutine

from fastmcp import Client
from fastmcp.client import FastMCPTransport

from .server import MAGGServer

logger = logging.getLogger(__name__)


class MAGGRunner:
    """Manages MAGG server lifecycle with proper signal handling."""
    _config_path: str | None
    _server: MAGGServer | None
    _shutdown_event: asyncio.Event
    _original_sigint: Callable | None
    _original_sigterm: Callable | None
    _hook_signals: bool

    def __init__(self, config_path: str | None = None, *, hook_signals: bool = True):
        self._config_path = config_path
        self._server = None
        self._shutdown_event = asyncio.Event()
        self._original_sigint = None
        self._original_sigterm = None
        self._hook_signals = hook_signals

    @cached_property
    def client(self) -> Client:
        """Create an in-memory client connected to the MAGG server. [cached]"""
        return Client(FastMCPTransport(self._server.mcp))

    @property
    def server(self) -> MAGGServer | None:
        """Get the current MAGG server instance."""
        return self._server

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
        if self._hook_signals:
            self._original_sigint = signal.signal(signal.SIGINT, self._handle_signal)
            self._original_sigterm = signal.signal(signal.SIGTERM, self._handle_signal)

    def _restore_signal_handlers(self):
        """Restore original signal handlers."""
        if self._hook_signals:
            if self._original_sigint:
                signal.signal(signal.SIGINT, self._original_sigint)
            if self._original_sigterm:
                signal.signal(signal.SIGTERM, self._original_sigterm)

    @asynccontextmanager
    async def _server_context(self):
        """Context manager for server lifecycle."""
        if self._server:
            raise RuntimeError("Server is already running")

        self._setup_signal_handlers()

        try:
            self._server = MAGGServer(self._config_path)
            await self._server.setup()
            yield self._server
        finally:
            self._restore_signal_handlers()

            if self._server:
                self._server = None

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
                logger.debug("Starting MAGG server in stdio mode")
                await self._serve(server.run_stdio())

        finally:
            logger.debug("MAGG server stopped")

    async def run_http(self, host: str = "localhost", port: int = 8000):
        """Run server in HTTP mode with proper signal handling."""
        try:
            async with self._server_context() as server:
                logger.debug("Starting MAGG HTTP server on %s:%s", host, port)
                await self._serve(server.run_http(host, port))

        finally:
            logger.debug("MAGG HTTP server stopped")
