"""Server runner utilities for Magg with proper signal handling."""

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from functools import cached_property
from pathlib import Path
from typing import Callable, Coroutine

from fastmcp import Client
from fastmcp.client import FastMCPTransport

from .server import MaggServer

logger = logging.getLogger(__name__)


class MaggRunner:
    """Manages Magg server lifecycle with proper signal handling."""

    # How long to wait for the server task to finish after cancelling it. The stdio transport
    # reads stdin in a worker thread that can't be interrupted, so its task may never finish.
    SHUTDOWN_TIMEOUT: float = 1.0

    _server: MaggServer
    _shutdown_event: asyncio.Event
    _reload_event: asyncio.Event
    _original_sigint: Callable | int | None
    _original_sigterm: Callable | int | None
    _original_sighup: Callable | int | None
    _signal_loop: asyncio.AbstractEventLoop | None = None
    _shutdown_signal: int | None = None
    _abandoned_task: bool = False
    _hook_signals: bool
    _hooked_signals: bool = False

    def __init__(
        self,
        config_path: Path | str | None = None,
        *,
        hook_signals: bool = True,
        env: dict | None = None,
    ):
        self._server = MaggServer(config_path, env=env)
        self._shutdown_event = asyncio.Event()
        self._reload_event = asyncio.Event()
        self._original_sigint = None
        self._original_sigterm = None
        self._original_sighup = None
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
    def _handle_signal(self, signum, frame=None):
        """Handle shutdown signals gracefully; a second signal forces exit."""
        signame = signal.Signals(signum).name

        if self._shutdown_event.is_set():
            logger.warning("Received %s again, forcing exit", signame)
            self._exit_by_signal(signum)
            return

        logger.debug("Received signal %s, shutting down gracefully...", signame)
        self._shutdown_signal = signum
        self._shutdown_event.set()

    @staticmethod
    def _exit_by_signal(signum):
        """Terminate the process with the signal's default action."""
        signal.signal(signum, signal.SIG_DFL)
        signal.raise_signal(signum)

    # noinspection PyUnusedLocal
    def _handle_reload_signal(self, signum, frame=None):
        """Handle reload signal (SIGHUP)."""
        logger.debug("Received SIGHUP, triggering config reload...")
        self._reload_event.set()

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown and reload."""
        if self._hook_signals and self._hooked_signals is False:
            handlers = {signal.SIGINT: self._handle_signal, signal.SIGTERM: self._handle_signal}
            # SIGHUP for config reload (Unix-like systems only)
            if hasattr(signal, "SIGHUP"):
                handlers[signal.SIGHUP] = self._handle_reload_signal

            self._original_sigint = signal.getsignal(signal.SIGINT)
            self._original_sigterm = signal.getsignal(signal.SIGTERM)
            if hasattr(signal, "SIGHUP"):
                self._original_sighup = signal.getsignal(signal.SIGHUP)

            loop = asyncio.get_running_loop()
            try:
                # Loop handlers run as loop callbacks, so they also wake an idle loop
                for signum, handler in handlers.items():
                    loop.add_signal_handler(signum, handler, signum)
                self._signal_loop = loop
            except (NotImplementedError, RuntimeError):
                # No loop signal support (e.g. Windows): hand the signal to the loop thread-safely
                for signum, handler in handlers.items():
                    signal.signal(signum, lambda s, _f, h=handler: loop.call_soon_threadsafe(h, s))
            self._hooked_signals = True

    def _restore_signal_handlers(self):
        """Restore original signal handlers."""
        if self._hook_signals and self._hooked_signals:
            originals = {signal.SIGINT: self._original_sigint, signal.SIGTERM: self._original_sigterm}
            if hasattr(signal, "SIGHUP"):
                originals[signal.SIGHUP] = self._original_sighup

            for signum, original in originals.items():
                if self._signal_loop is not None:
                    self._signal_loop.remove_signal_handler(signum)
                # SIG_DFL is 0, so check against None rather than truthiness
                if original is not None:
                    signal.signal(signum, original)

            self._signal_loop = None
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

            # asyncio.run() would wait forever on an abandoned server task, so now that cleanup
            # is done, finish the signal-requested shutdown with the signal's default action
            if self._abandoned_task and self._shutdown_signal is not None:
                logger.debug("Magg server stopped, exiting with abandoned server task")
                self._exit_by_signal(self._shutdown_signal)

    async def _serve(self, coro: Coroutine):
        server_task = asyncio.create_task(coro)
        shutdown_task = asyncio.create_task(self._shutdown_event.wait())
        reload_task = asyncio.create_task(self._handle_reload_events())

        done, pending = await asyncio.wait([server_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED)

        # Cancel reload task
        reload_task.cancel()
        try:
            await reload_task
        except asyncio.CancelledError:
            pass

        for task in pending:
            task.cancel()

        if pending:
            _, stuck = await asyncio.wait(pending, timeout=self.SHUTDOWN_TIMEOUT)
            if stuck:
                logger.debug("Server task did not stop within %ss, abandoning it", self.SHUTDOWN_TIMEOUT)
                self._abandoned_task = True

        for task in done:
            if task is server_task and task.exception():
                logger.error("Server task failed with exception: %s", task.exception())
                raise task.exception()

    async def _handle_reload_events(self):
        """Handle reload events triggered by SIGHUP."""
        while True:
            await self._reload_event.wait()
            self._reload_event.clear()

            try:
                logger.debug("Processing config reload request...")
                success = await self._server.reload_config()
                if success:
                    logger.debug("Config reload completed successfully")
                else:
                    logger.error("Config reload failed")
            except Exception as e:
                logger.error("Error during config reload: %s", e)

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
        self._server.server_manager.require_http_auth()

        try:
            async with self._server_context() as server:
                logger.debug("Starting Magg HTTP server on %s:%s", host, port)
                await self._serve(server.run_http(host, port))

        finally:
            logger.debug("Magg HTTP server stopped")

    async def run_hybrid(self, host: str = "localhost", port: int = 8000):
        """Run server in hybrid mode (stdio + HTTP) with proper signal handling."""
        self._server.server_manager.require_http_auth()

        try:
            async with self._server_context() as server:
                logger.debug("Starting Magg hybrid server (stdio + HTTP on %s:%s)", host, port)
                await self._serve(server.run_hybrid(host, port))

        finally:
            logger.debug("Magg hybrid server stopped")

    async def start_stdio(self) -> asyncio.Task:
        """Start the server in stdio mode in a different task."""
        return asyncio.create_task(self.run_stdio())

    async def start_http(self, host: str = "localhost", port: int = 8000) -> asyncio.Task:
        """Start the server in HTTP mode in a different task."""
        return asyncio.create_task(self.run_http(host, port))
