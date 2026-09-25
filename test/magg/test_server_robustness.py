"""Robustness tests: unmounting, hung backends, read-only mode, auth, signals, and related fixes."""

import asyncio
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client
from pydantic import AnyUrl

from magg.reload import ConfigChange, ServerChange
from magg.server.runner import MaggRunner
from magg.server.server import MaggServer
from magg.settings import ServerConfig

BACKEND_CODE = '''
import sys

from fastmcp import FastMCP

label = sys.argv[1] if len(sys.argv) > 1 else "default"
mcp = FastMCP("backend")


@mcp.tool
def greet(name: str) -> str:
    """Greet someone."""
    return f"{label}: hello {name}"


if __name__ == "__main__":
    mcp.run(show_banner=False)
'''


@pytest.fixture
def backend_script(tmp_path) -> Path:
    path = tmp_path / "backend.py"
    path.write_text(BACKEND_CODE)
    return path


def backend_config(name: str, script: Path, label: str, prefix: str | None = None, **kwds) -> ServerConfig:
    return ServerConfig(
        name=name, source="test", command=sys.executable, args=[str(script), label], prefix=prefix, **kwds
    )


def write_config(path: Path, servers: dict[str, ServerConfig]):
    data = {
        "servers": {
            name: server.model_dump(mode="json", exclude_none=True, exclude={"name"})
            for name, server in servers.items()
        }
    }
    path.write_text(json.dumps(data))


async def tool_names(client: Client) -> list[str]:
    return [tool.name for tool in await client.list_tools()]


def response_output(result) -> dict:
    return json.loads(result.content[0].text)


class TestUnmount:
    """Unmounting removes a backend's provider from FastMCP."""

    @pytest.mark.asyncio
    async def test_disable_enable_remove(self, tmp_path, backend_script):
        config_path = tmp_path / "config.json"
        write_config(config_path, {"bk": backend_config("bk", backend_script, "one", prefix="bk")})
        server = MaggServer(config_path, enable_config_reload=False)

        async with server:
            providers_before = len(server.mcp.providers)

            async with Client(server.mcp) as client:
                assert (await tool_names(client)).count("bk_greet") == 1

                result = response_output(await client.call_tool("magg_disable_server", {"name": "bk"}))
                assert result["errors"] is None
                assert "bk_greet" not in await tool_names(client)
                assert len(server.mcp.providers) == providers_before - 1

                result = response_output(await client.call_tool("magg_enable_server", {"name": "bk"}))
                assert result["output"]["mounted"] is True
                assert (await tool_names(client)).count("bk_greet") == 1
                assert len(server.mcp.providers) == providers_before

                greeting = await client.call_tool("bk_greet", {"name": "x"})
                assert greeting.content[0].text == "one: hello x"

                result = response_output(await client.call_tool("magg_remove_server", {"name": "bk"}))
                assert result["errors"] is None
                assert "bk_greet" not in await tool_names(client)
                assert len(server.mcp.providers) == providers_before - 1

    @pytest.mark.asyncio
    async def test_update_applies_new_args_and_prefix(self, tmp_path, backend_script):
        config_path = tmp_path / "config.json"
        old = backend_config("bk", backend_script, "old", prefix="old")
        write_config(config_path, {"bk": old})
        server = MaggServer(config_path, enable_config_reload=False)

        async with server:
            async with Client(server.mcp) as client:
                assert (await client.call_tool("old_greet", {"name": "x"})).content[0].text == "old: hello x"

                new = backend_config("bk", backend_script, "new", prefix="new")
                config = server.config
                change = ConfigChange(
                    old_config=config,
                    new_config=config,
                    server_changes=[ServerChange(name="bk", action="update", old_config=old, new_config=new)],
                )
                await server.server_manager.handle_config_reload(change)

                names = await tool_names(client)
                assert "old_greet" not in names
                assert names.count("new_greet") == 1
                assert (await client.call_tool("new_greet", {"name": "x"})).content[0].text == "new: hello x"


class TestCheck:
    """magg_check works on mounted servers without breaking them."""

    @pytest.mark.asyncio
    async def test_check_mounted_server(self, tmp_path, backend_script):
        config_path = tmp_path / "config.json"
        write_config(config_path, {"bk": backend_config("bk", backend_script, "one", prefix="bk")})
        server = MaggServer(config_path, enable_config_reload=False)

        async with server:
            async with Client(server.mcp) as client:
                assert (await client.call_tool("bk_greet", {"name": "a"})).content[0].text == "one: hello a"

                result = response_output(await client.call_tool("magg_check", {"timeout": 20}))
                assert result["errors"] is None
                assert result["output"]["results"]["bk"]["status"] == "healthy"
                assert result["output"]["healthy"] == 1

                # The mounted proxy still works after the check used the backend client
                assert (await client.call_tool("bk_greet", {"name": "b"})).content[0].text == "one: hello b"


class TestHungBackend:
    """A backend that never initializes degrades only itself."""

    @pytest.mark.asyncio
    async def test_hung_backend(self, tmp_path, backend_script, monkeypatch):
        monkeypatch.setenv("MAGG_BACKEND_INIT_TIMEOUT", "2")
        config_path = tmp_path / "config.json"
        hung = ServerConfig(
            name="hung", source="test", command=sys.executable, args=["-c", "import time; time.sleep(1000)"]
        )
        write_config(config_path, {"hung": hung, "good": backend_config("good", backend_script, "g", prefix="good")})
        server = MaggServer(config_path, enable_config_reload=False)

        async with server:
            assert server.server_manager.mounted_servers["hung"].client._init_timeout == 2.0

            async with Client(server.mcp) as client:
                start = time.monotonic()
                names = await tool_names(client)
                assert time.monotonic() - start < 10
                assert "magg_list_servers" in names
                assert "good_greet" in names

                # Magg's own tools resolve without waiting on the hung backend
                start = time.monotonic()
                result = response_output(await client.call_tool("magg_list_servers", {}))
                assert time.monotonic() - start < 1.5
                assert {s["name"] for s in result["output"]} == {"hung", "good"}

                assert (await client.call_tool("good_greet", {"name": "x"})).content[0].text == "g: hello x"

    @pytest.mark.asyncio
    async def test_init_timeout_zero_waits_forever(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAGG_BACKEND_INIT_TIMEOUT", "0")
        server = MaggServer(tmp_path / "config.json", enable_config_reload=False)
        assert await server.server_manager.mount_server(ServerConfig(name="s", source="t", command="true"))
        assert server.server_manager.mounted_servers["s"].client._init_timeout is None
        await server.server_manager.unmount_server("s")


class TestTransportSetup:
    """Backend env precedence and stderr handling."""

    @pytest.mark.asyncio
    async def test_server_env_overrides_passed_env(self, tmp_path):
        server = MaggServer(tmp_path / "config.json", enable_config_reload=False, env={"FOO": "outer", "BAR": "b"})
        config = ServerConfig(name="s", source="t", command="true", env={"FOO": "server"})
        assert await server.server_manager.mount_server(config)
        env = server.server_manager.mounted_servers["s"].client.transport.env
        assert env["FOO"] == "server"
        assert env["BAR"] == "b"
        await server.server_manager.unmount_server("s")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("show", [False, True])
    async def test_stderr_log_file(self, tmp_path, monkeypatch, show):
        monkeypatch.setenv("MAGG_STDERR_SHOW", str(show).lower())
        server = MaggServer(tmp_path / "config.json", enable_config_reload=False)
        assert await server.server_manager.mount_server(ServerConfig(name="s", source="t", command="true"))
        log_file = server.server_manager.mounted_servers["s"].client.transport.log_file
        assert log_file == (None if show else Path(os.devnull))
        await server.server_manager.unmount_server("s")


class TestAddServer:
    """add_server input handling and rollback."""

    @pytest.mark.asyncio
    async def test_add_with_uri(self, tmp_path):
        server = MaggServer(tmp_path / "config.json", enable_config_reload=False)

        async with Client(server.mcp) as client:
            result = response_output(
                await client.call_tool(
                    "magg_add_server",
                    {"name": "web", "source": "test", "uri": "http://localhost:9/mcp", "enable": False},
                )
            )
        assert result["errors"] is None
        assert server.config.servers["web"].uri == "http://localhost:9/mcp"

        response = await server.add_server(name="web2", source="test", uri=AnyUrl("http://localhost:9/mcp"))
        assert response.is_success
        assert "web2" in server.server_manager.mounted_servers

    @pytest.mark.asyncio
    async def test_add_requires_command_or_uri(self, tmp_path):
        server = MaggServer(tmp_path / "config.json", enable_config_reload=False)

        for enable in (True, False):
            response = await server.add_server(name="empty", source="test", enable=enable)
            assert response.is_error
            assert "provide either command or uri" in response.errors[0]
        assert "empty" not in server.config.servers

    @pytest.mark.asyncio
    async def test_mount_failure_reason(self, tmp_path):
        server = MaggServer(tmp_path / "config.json", enable_config_reload=False)

        with patch("magg.server.manager.get_transport_for_command", side_effect=ValueError("no such tool")):
            response = await server.add_server(name="bad", source="test", command="whatever")

        assert response.is_error
        assert "no such tool" in response.errors[0]
        assert "bad" not in server.config.servers

    @pytest.mark.asyncio
    async def test_add_rolls_back_mount_when_save_fails(self, tmp_path):
        server = MaggServer(tmp_path / "config.json", enable_config_reload=False)
        providers_before = len(server.mcp.providers)

        with patch.object(server, "save_config", return_value=False):
            response = await server.add_server(name="s", source="test", command="true")

        assert response.is_error
        assert "s" not in server.server_manager.mounted_servers
        assert len(server.mcp.providers) == providers_before


class TestReadOnly:
    """Mutating tools refuse up front in read-only mode."""

    @pytest.fixture
    def server(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        write_config(config_path, {"s": ServerConfig(name="s", source="t", command="true", enabled=False)})
        monkeypatch.setenv("MAGG_READ_ONLY", "true")
        return MaggServer(config_path, enable_config_reload=False)

    @pytest.mark.asyncio
    async def test_mutating_tools_refuse(self, server):
        server.server_manager.mount_server = AsyncMock(return_value=True)
        server.server_manager.unmount_server = AsyncMock(return_value=True)
        server.kit_manager.load_kit_to_config = MagicMock()
        server.kit_manager.unload_kit_from_config = MagicMock()

        responses = [
            await server.add_server(name="new", source="test", command="true"),
            await server.remove_server(name="s"),
            await server.enable_server(name="s"),
            await server.disable_server(name="s"),
            await server.load_kit(name="k"),
            await server.unload_kit(name="k"),
            await server.check(action="disable"),
            await server.check(action="unmount"),
        ]

        for response in responses:
            assert response.is_error
            assert "read-only" in response.errors[0]

        server.server_manager.mount_server.assert_not_called()
        server.server_manager.unmount_server.assert_not_called()
        server.kit_manager.load_kit_to_config.assert_not_called()
        server.kit_manager.unload_kit_from_config.assert_not_called()
        assert set(server.config.servers) == {"s"}

    @pytest.mark.asyncio
    async def test_check_report_allowed(self, server):
        response = await server.check(action="report")
        assert response.is_success


class TestAuthFailClosed:
    """An unloadable private key refuses HTTP instead of serving without auth."""

    @pytest.mark.asyncio
    async def test_bad_private_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAGG_PRIVATE_KEY", "not a key")
        runner = MaggRunner(tmp_path / "config.json")
        server = runner.server

        assert "MAGG_PRIVATE_KEY" in server.server_manager.auth_error
        assert server.mcp.auth is None

        with patch.object(server.server_manager, "mount_all_enabled", new_callable=AsyncMock) as mount_all:
            for run in (runner.run_http, runner.run_hybrid, server.run_http, server.run_hybrid):
                with pytest.raises(RuntimeError, match="MAGG_PRIVATE_KEY.*refusing to serve HTTP"):
                    await run()
            mount_all.assert_not_called()


class TestRunnerSignals:
    """Shutdown signals wake the loop, restore handlers, and escalate on repeat."""

    @pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="POSIX signals required")
    @pytest.mark.asyncio
    async def test_sigterm_wakes_idle_loop_and_restores_default(self, tmp_path):
        runner = MaggRunner(tmp_path / "config.json")

        async def idle():
            await asyncio.Event().wait()

        previous = signal.signal(signal.SIGTERM, signal.SIG_DFL)
        try:
            async with runner._server_context():
                serve_task = asyncio.create_task(runner._serve(idle()))
                await asyncio.sleep(0.1)
                os.kill(os.getpid(), signal.SIGTERM)
                await asyncio.wait_for(serve_task, 5)

            # SIG_DFL is falsy, but must still be restored
            assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
        finally:
            signal.signal(signal.SIGTERM, previous)

    def test_second_signal_forces_exit(self, tmp_path):
        runner = MaggRunner(tmp_path / "config.json")

        with patch.object(MaggRunner, "_exit_by_signal") as exit_by_signal:
            runner._handle_signal(signal.SIGINT)
            assert runner._shutdown_event.is_set()
            exit_by_signal.assert_not_called()

            runner._handle_signal(signal.SIGINT)
            exit_by_signal.assert_called_once_with(signal.SIGINT)

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals required")
    def test_stdio_serve_exits_on_sigterm(self, tmp_path):
        env = {**os.environ, "MAGG_CONFIG_PATH": str(tmp_path / "config.json"), "MAGG_LOG_LEVEL": "WARNING"}
        proc = subprocess.Popen(
            [sys.executable, "-m", "magg", "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        try:
            init = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"},
                },
            }
            proc.stdin.write((json.dumps(init) + "\n").encode())
            proc.stdin.flush()
            assert select.select([proc.stdout], [], [], 30)[0], "server did not respond"
            assert b'"id":1' in proc.stdout.readline()  # Server is up; stdin stays open

            proc.send_signal(signal.SIGTERM)
            start = time.monotonic()
            proc.wait(timeout=15)
            assert time.monotonic() - start < 5
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def test_proxy_path_description(tmp_path):
    server = MaggServer(tmp_path / "config.json", enable_config_reload=False)
    tool = asyncio.run(server.mcp.get_tool("proxy"))
    description = tool.parameters["properties"]["path"]["description"]
    assert "Required for 'info' and 'call'" in description
