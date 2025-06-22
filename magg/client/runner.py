"""Client-side runner for embedding MAGG in user applications."""
import asyncio
import threading
from typing import Literal
from dataclasses import dataclass
import socket
from functools import cached_property

from magg.server import MAGGServer
from fastmcp import Client


@dataclass
class ConnectionInfo:
    """Connection information for MAGG server."""
    transport: Literal["stdio", "http"]
    host: str | None = None
    port: int | None = None

    @property
    def url(self) -> str | None:
        if self.transport == "http" and self.host is not None and self.port is not None:
            return f"http://{self.host}:{self.port}/mcp/"
        return None

    @cached_property
    def client(self) -> Client:
        """Create a FastMCP client for this connection."""
        if self.transport == "http":
            if not self.url:
                raise RuntimeError("No URL available for HTTP transport")
            return Client(self.url)
        elif self.transport == "stdio":
            # For stdio, we'd need to pass the subprocess pipes
            # This would require the runner to store them in ConnectionInfo
            raise NotImplementedError("stdio client creation not yet implemented")
        else:
            raise ValueError(f"Unsupported transport: {self.transport}")


class MAGGRunner:
    """Run MAGG server for embedding in applications.

    Can be used in both sync and async contexts:

    Sync usage:
        with MAGGRunner() as client:
            with client.connect() as session:
                # use session

    Async usage:
        async with MAGGRunner() as client:
            async with client.connect() as session:
                # use session
    """

    def __init__(
        self,
        config_path: str | None = None,
        transport: Literal["stdio", "http"] = "stdio",
        host: str | None = None,
        port: int | None = None,
    ):
        self.config_path = config_path
        self.transport = transport

        if transport == "stdio":
            if host is not None or port is not None:
                raise ValueError("stdio transport does not support host or port parameters")
            self.host = None
            self.port = None
        elif transport == "http":
            self.host = host or "localhost"
            self.port = port if port is not None else 0
        else:
            raise ValueError(f"Unsupported transport: {transport}")

        # For sync operation (running in thread)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = threading.Event()
        self._stopped = threading.Event()

        # For async operation (running as task)
        self._server: MAGGServer | None = None
        self._server_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

        # Shared
        self._connection_info: ConnectionInfo | None = None
        self._is_async = False

    def start(self) -> ConnectionInfo:
        """Start MAGG server in background thread (for sync usage)."""
        if self._is_async:
            raise RuntimeError("Cannot use sync start() after async operations")

        if self._thread and self._thread.is_alive():
            return self._connection_info

        # Find free port if needed
        if self.transport == "http" and self.port == 0:
            with socket.socket() as s:
                s.bind((self.host, 0))
                self.port = s.getsockname()[1]

        # Set connection info
        self._connection_info = ConnectionInfo(
            transport=self.transport,
            host=self.host if self.transport == "http" else None,
            port=self.port if self.transport == "http" else None,
        )

        # Start server in thread
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run_thread, daemon=True)
        self._thread.start()

        # Wait for server to start
        if not self._started.wait(timeout=5):
            raise RuntimeError("Server failed to start within 5 seconds")

        return self._connection_info

    def _run_thread(self):
        """Run asyncio event loop in thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._run_async_in_thread())
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self._loop.close()
            asyncio.set_event_loop(None)

    async def _run_async_in_thread(self):
        """Run the async server in thread's event loop."""
        server = MAGGServer(self.config_path)
        await server.setup()

        # Create server task
        if self.transport == "stdio":
            server_task = asyncio.create_task(server.run_stdio())
        elif self.transport == "http":
            server_task = asyncio.create_task(server.run_http(self.host, self.port))
        else:
            raise ValueError(f"Unsupported transport: {self.transport}")

        # Signal that server has started
        self._started.set()

        # Wait for stop signal
        stop_task = asyncio.create_task(self._wait_for_stop())

        done, pending = await asyncio.wait(
            [server_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _wait_for_stop(self):
        """Wait for stop signal from another thread."""
        while not self._stopped.is_set():
            await asyncio.sleep(0.1)

    def stop(self):
        """Stop the server (sync version)."""
        if self._thread and self._thread.is_alive():
            self._stopped.set()
            self._thread.join(timeout=5)
            self._started.clear()

    def join(self, timeout: float | None = None):
        """Block until the server stops (sync version)."""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    async def astart(self) -> ConnectionInfo:
        """Start MAGG server (for async usage)."""
        self._is_async = True

        if self._server_task and not self._server_task.done():
            return self._connection_info

        # Find free port if needed
        if self.transport == "http" and self.port == 0:
            with socket.socket() as s:
                s.bind((self.host, 0))
                self.port = s.getsockname()[1]

        # Create and setup server
        self._server = MAGGServer(self.config_path)
        await self._server.setup()

        # Set connection info
        self._connection_info = ConnectionInfo(
            transport=self.transport,
            host=self.host if self.transport == "http" else None,
            port=self.port if self.transport == "http" else None,
        )

        # Initialize stop event
        self._stop_event = asyncio.Event()

        # Start server task
        self._server_task = asyncio.create_task(self._run_server_async())

        # Give it a moment to start
        await asyncio.sleep(0.1)

        return self._connection_info

    async def _run_server_async(self):
        """Run server until stopped (async version)."""
        try:
            if self.transport == "stdio":
                server_coro = self._server.run_stdio()
            elif self.transport == "http":
                server_coro = self._server.run_http(self.host, self.port)
            else:
                raise ValueError(f"Unsupported transport: {self.transport}")

            # Run server alongside stop event
            server_task = asyncio.create_task(server_coro)
            stop_task = asyncio.create_task(self._stop_event.wait())

            done, pending = await asyncio.wait(
                [server_task, stop_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            print(f"Server error: {e}")

    async def astop(self):
        """Stop the server (async version)."""
        if self._server_task and not self._server_task.done():
            self._stop_event.set()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
            self._stop_event.clear()

    async def ajoin(self):
        """Wait until the server stops (async version)."""
        if self._server_task and not self._server_task.done():
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

    @property
    def connection_info(self) -> ConnectionInfo | None:
        """Get connection info."""
        return self._connection_info

    # Sync context manager
    def __enter__(self):
        self.start()
        return self._connection_info.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    # Async context manager
    async def __aenter__(self):
        await self.astart()
        return self._connection_info.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.astop()
