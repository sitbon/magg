"""Tests for mbro command handling: argument parsing, errors, exit codes."""

import shutil
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client, FastMCP

from magg.mbro import cli as cli_module
from magg.mbro.cli import MCPBrowserCLI, main_async
from magg.mbro.client import BrowserConnection
from magg.mbro.parser import CommandParser


def make_server() -> FastMCP:
    mcp = FastMCP("test")

    @mcp.tool(description="Echo a string value")
    def echo(value: str) -> str:
        return f"echo:{value!r}"

    @mcp.tool
    def nodesc(n: int) -> str:
        return f"n:{n!r}"

    @mcp.tool
    def anyval(value: object = None) -> str:
        return f"any:{value!r}"

    @mcp.prompt
    def greet(name: str) -> str:
        return f"Hello {name}"

    @mcp.resource("res://nodesc")
    def nodesc_res() -> str:
        return "resource-content"

    return mcp


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("MAGG_PATH", str(tmp_path))
    monkeypatch.setenv("MAGG_CONFIG_PATH", str(tmp_path / "config.json"))
    return MCPBrowserCLI(use_rich=False)


async def run(cli: MCPBrowserCLI, *commands: str) -> bool:
    """Run commands, returning whether all of them succeeded."""
    return await cli.run_commands(list(commands))


def attach(cli: MCPBrowserCLI, name: str = "t") -> None:
    """Attach an in-memory connection to the test server."""
    conn = BrowserConnection(name, "memory", "memory")
    conn.client = Client(make_server())
    conn.connected = True
    cli.browser.connections[name] = conn
    cli.browser.current_connection = name


class TestJsonArguments:
    """JSON arguments for call/prompt keep their inner quotes."""

    def test_unquoted_json(self):
        parts = CommandParser.parse_command_line('call echo {"value": "hello world"}')
        assert parts == ["call", "echo", '{"value": "hello world"}']

    def test_quoted_json(self):
        parts = CommandParser.parse_command_line("""call echo '{"value": "hello world"}'""")
        assert parts == ["call", "echo", '{"value": "hello world"}']

    def test_prompt_json(self):
        parts = CommandParser.parse_command_line('prompt greet {"name": "Bob"}')
        assert parts == ["prompt", "greet", '{"name": "Bob"}']

    def test_other_commands_still_shell_split(self):
        assert CommandParser.parse_command_line('search "a b"') == ["search", "a b"]

    def test_multiline_json_in_script(self):
        script = (
            "connect t python server.py\n"
            "call echo {\n"
            '  "value": "a # b; c",  # trailing comment\n'
            "\n"
            "  \"other\": 'x'\n"
            "}\n"
            "tools\n"
        )
        assert CommandParser.split_commands(script) == [
            "connect t python server.py",
            'call echo {\n  "value": "a # b; c",\n\n  "other": \'x\'\n}',
            "tools",
        ]

    def test_braces_in_quotes_do_not_join_lines(self):
        commands = CommandParser.split_commands('call echo value="{"\ntools')
        assert commands == ['call echo value="{"', "tools"]

    @pytest.mark.asyncio
    async def test_call_forms(self, cli, capsys):
        attach(cli)
        commands = [
            "call echo value=kv",
            'call echo {"value": "unquoted"}',
            """call echo '{"value": "quoted"}'""",
            *CommandParser.split_commands('call echo {\n  "value": "multi"\n}'),
        ]
        assert await cli.run_commands(commands)

        out = capsys.readouterr().err
        for value in ("kv", "unquoted", "quoted", "multi"):
            assert f"echo:'{value}'" in out

    @pytest.mark.asyncio
    async def test_invalid_json_fails(self, cli, capsys):
        attach(cli)
        assert not await run(cli, "call echo {value: 1}")
        assert "Invalid JSON arguments" in capsys.readouterr().err


class TestValueParsing:
    """key=value parsing for call/prompt."""

    def test_without_schema(self):
        args = ["a=007", "b=10-20", "c=5-", "d=null", "e=[1,2]", "f=1e5", "g=42", "h=-3", "i=True", "j=my server"]
        assert MCPBrowserCLI.parse_shell_args(args) == {
            "a": "007",
            "b": "10-20",
            "c": "5-",
            "d": None,
            "e": [1, 2],
            "f": 100000.0,
            "g": 42,
            "h": -3,
            "i": True,
            "j": "my server",
        }

    def test_string_params_stay_strings(self):
        schema = {
            "properties": {
                "s": {"type": "string"},
                "opt": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "n": {"type": "integer"},
                "u": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            }
        }
        args = ["s=123", "opt=true", "n=5", "u=5"]
        assert MCPBrowserCLI.parse_shell_args(args, schema) == {"s": "123", "opt": "true", "n": 5, "u": 5}

    def test_strings_flag(self):
        assert MCPBrowserCLI.parse_shell_args(["a=5", "b=null"], strings=True) == {"a": "5", "b": "null"}

    @pytest.mark.asyncio
    async def test_call_uses_schema(self, cli, capsys):
        attach(cli)
        assert await cli.run_commands(["call echo value=10-20", "call echo value=007", "call nodesc n=5"])

        out = capsys.readouterr().err
        assert "echo:'10-20'" in out
        assert "echo:'007'" in out
        assert "n:5" in out

    @pytest.mark.asyncio
    async def test_prompt_key_value(self, cli, capsys):
        attach(cli)
        assert await run(cli, "prompt greet name=Bob")
        assert "Hello Bob" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_positional_rejected(self, cli, capsys):
        attach(cli)
        assert not await run(cli, "prompt greet Bob")
        assert "Positional arguments are not supported" in capsys.readouterr().err


class TestCommands:
    """Individual command behavior."""

    @pytest.mark.asyncio
    async def test_status_without_connection(self, cli, capsys):
        assert not await run(cli, "status")
        assert "No active connection" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_status(self, cli, capsys):
        attach(cli)
        assert await run(cli, "status")
        assert '"tools": 3' in capsys.readouterr().out

    @pytest.mark.asyncio
    @pytest.mark.parametrize("command", ["tools zzz", "prompts zzz", "search zzz", "search nodesc"])
    async def test_none_descriptions(self, cli, command):
        attach(cli)
        assert await run(cli, command)

    @pytest.mark.asyncio
    async def test_search_json_resource_without_description(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("MAGG_PATH", str(tmp_path))
        cli = MCPBrowserCLI(json_only=True, use_rich=False)
        attach(cli)
        assert await run(cli, "search nodesc")
        out = capsys.readouterr().out
        assert '"nodesc_res"' in out

    @pytest.mark.asyncio
    async def test_unknown_tool_suggestion(self, cli, capsys):
        attach(cli)
        assert not await run(cli, "call ech value=x")
        assert "Did you mean: echo?" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_duplicate_connection_name(self, cli, capsys):
        attach(cli)
        assert not await run(cli, "connect t python server.py")
        assert "connection name 't' already exists" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_connect_failure_reason(self, cli, capfd):
        # capfd rather than capsys: the stdio transport needs a real stderr fd
        assert not await run(cli, "connect nx this-command-does-not-exist-mbro")
        assert "No such file or directory" in capfd.readouterr().err

    @pytest.mark.asyncio
    @pytest.mark.skipif(not shutil.which("sleep"), reason="needs sleep")
    async def test_connect_timeout(self):
        conn = BrowserConnection("s", "command", "sleep 100")
        with pytest.raises(TimeoutError, match="0.5s"):
            await conn.connect(timeout=0.5)

    @pytest.mark.asyncio
    async def test_missing_script_does_not_exit(self, cli, capsys):
        assert not await run(cli, "script run nope")
        assert "Script not found" in capsys.readouterr().err
        assert cli.running

    @pytest.mark.asyncio
    async def test_repl_without_arepl(self, cli, capsys):
        with patch.object(cli_module, "arepl", None):
            await cli.start(repl=True)
        assert "only available" in capsys.readouterr().err


class TestUrlNormalization:
    @pytest.mark.parametrize(
        "url, expected",
        [
            ("http://h:1", "http://h:1/mcp/"),
            ("http://h:1/", "http://h:1/mcp/"),
            ("http://h:1?x=1", "http://h:1/mcp/?x=1"),
            ("http://h:1/mcp", "http://h:1/mcp"),
            ("http://h:1/mcp/", "http://h:1/mcp/"),
            ("http://h:1/sse", "http://h:1/sse"),
            ("https://h/api/mcp", "https://h/api/mcp"),
        ],
    )
    def test_normalize_url(self, url, expected):
        assert BrowserConnection.normalize_url(url) == expected


class TestBatchExecution:
    """Error handling and exit codes when running command batches."""

    @pytest.mark.asyncio
    async def test_continues_after_failures(self, cli, capsys):
        attach(cli)
        assert not await cli.run_commands(["bogus", "call echo value=after"])
        assert cli.failed
        assert "echo:'after'" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_unexpected_exception_is_contained(self, cli, capsys):
        attach(cli)
        with patch.object(cli.command, "tools", AsyncMock(side_effect=RuntimeError("boom"))):
            assert not await cli.run_commands(["tools", "call echo value=after"])
        assert "echo:'after'" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_fail_fast(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("MAGG_PATH", str(tmp_path))
        cli = MCPBrowserCLI(use_rich=False, fail_fast=True)
        attach(cli)
        assert not await cli.run_commands(["bogus", "call echo value=after"])
        assert "echo:'after'" not in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_quit_stops_script(self, cli, tmp_path, capsys):
        attach(cli)
        script = tmp_path / "s.mbro"
        script.write_text("call echo value=before\nquit\ncall echo value=after\n")
        assert await cli.run_commands([f"script run {script}", "call echo value=next"])

        out = capsys.readouterr().err
        assert "echo:'before'" in out
        assert "after" not in out
        assert "next" not in out

    @staticmethod
    async def run_main(monkeypatch, *argv: str) -> int:
        monkeypatch.setattr(sys, "argv", ["mbro", "--no-rich", *argv])
        try:
            await main_async()
        except SystemExit as e:
            return e.code
        return 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "command, code",
        [("help", 0), ("bogus", 1), ("status", 1), ("tools", 1), ('call echo {"value": 1}', 1)],
    )
    async def test_exit_codes(self, command, code, tmp_path, monkeypatch):
        monkeypatch.setenv("MAGG_PATH", str(tmp_path))
        assert await self.run_main(monkeypatch, "-n", command) == code

    @pytest.mark.asyncio
    async def test_script_exit_code(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAGG_PATH", str(tmp_path))
        assert await self.run_main(monkeypatch, "-X", str(tmp_path / "missing.mbro")) == 1

    @pytest.mark.asyncio
    async def test_stdin_is_non_interactive(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAGG_PATH", str(tmp_path))
        with (
            patch("sys.stdin.read", return_value="help\n"),
            patch.object(MCPBrowserCLI, "start", AsyncMock()) as start,
        ):
            assert await self.run_main(monkeypatch, "-") == 0
        start.assert_not_called()
