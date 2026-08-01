"""Tests for server CLI commands (add, update, list, info)."""

import json

import pytest
import pytest_asyncio

from magg.cli import cmd_server, create_parser
from magg.settings import ConfigManager


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """Isolated config file path for CLI runs."""
    monkeypatch.setenv("MAGG_PATH", str(tmp_path / ".magg"))
    monkeypatch.delenv("MAGG_CONFIG_PATH", raising=False)
    monkeypatch.delenv("MAGG_READ_ONLY", raising=False)
    return tmp_path / ".magg" / "config.json"


def parse(config_path, *argv):
    """Parse CLI arguments the same way main() does."""
    return create_parser().parse_args(["--config", str(config_path), *argv])


async def run_server_cmd(config_path, *argv) -> int:
    args = parse(config_path, "server", *argv)
    return await cmd_server(args) or 0


def load_servers(config_path):
    return ConfigManager(config_path).load_config().servers


class TestServerAddCLI:
    """Test magg server add."""

    @pytest.mark.asyncio
    async def test_add_basic(self, config_path, capsys):
        result = await run_server_cmd(
            config_path,
            "add",
            "calc",
            "https://example.com/calc",
            "--command",
            "npx -y calculator-mcp",
            "--prefix",
            "calc",
        )
        assert result == 0

        servers = load_servers(config_path)
        assert servers["calc"].command == "npx"
        assert servers["calc"].args == ["-y", "calculator-mcp"]
        assert servers["calc"].prefix == "calc"
        assert servers["calc"].enabled is True

        captured = capsys.readouterr()
        assert "Added server 'calc'" in captured.err

    @pytest.mark.asyncio
    async def test_add_shlex_command_parsing(self, config_path):
        """Quoted arguments in --command are preserved as single args."""
        result = await run_server_cmd(
            config_path,
            "add",
            "quoted",
            "https://example.com",
            "--command",
            'python -c "import this"',
        )
        assert result == 0

        servers = load_servers(config_path)
        assert servers["quoted"].command == "python"
        assert servers["quoted"].args == ["-c", "import this"]

    @pytest.mark.asyncio
    async def test_add_disabled_with_transport(self, config_path):
        result = await run_server_cmd(
            config_path,
            "add",
            "web",
            "https://example.com/web",
            "--uri",
            "http://localhost:9000/mcp",
            "--transport",
            '{"keep_alive": false}',
            "--disable",
        )
        assert result == 0

        servers = load_servers(config_path)
        assert servers["web"].enabled is False
        assert servers["web"].transport == {"keep_alive": False}

    @pytest.mark.asyncio
    async def test_add_invalid_transport(self, config_path, capsys):
        result = await run_server_cmd(
            config_path,
            "add",
            "bad",
            "https://example.com",
            "--transport",
            "not-json",
        )
        assert result == 1
        assert "bad" not in load_servers(config_path)

        captured = capsys.readouterr()
        assert "Invalid transport configuration" in captured.err

    @pytest.mark.asyncio
    async def test_add_transport_must_be_object(self, config_path, capsys):
        result = await run_server_cmd(
            config_path,
            "add",
            "bad",
            "https://example.com",
            "--transport",
            '["not", "an", "object"]',
        )
        assert result == 1

        captured = capsys.readouterr()
        assert "must be a JSON object" in captured.err

    @pytest.mark.asyncio
    async def test_add_unbalanced_quotes_rejected(self, config_path, capsys):
        result = await run_server_cmd(config_path, "add", "bad", "https://example.com", "--command", 'echo "unclosed')
        assert result == 1
        assert "bad" not in load_servers(config_path)

        captured = capsys.readouterr()
        assert "Invalid command" in captured.err

    @pytest.mark.asyncio
    async def test_add_duplicate(self, config_path, capsys):
        assert await run_server_cmd(config_path, "add", "calc", "https://example.com") == 0
        result = await run_server_cmd(config_path, "add", "calc", "https://example.com")
        assert result == 1

        captured = capsys.readouterr()
        assert "already exists" in captured.err


class TestServerUpdateCLI:
    """Test magg server update."""

    @pytest_asyncio.fixture
    async def populated_config(self, config_path):
        await run_server_cmd(
            config_path,
            "add",
            "calc",
            "https://example.com/calc",
            "--command",
            "npx -y calculator-mcp",
            "--prefix",
            "calc",
            "--env",
            "KEY=VALUE",
            "--notes",
            "original notes",
        )
        return config_path

    @pytest.mark.asyncio
    async def test_update_fields(self, populated_config, capsys):
        result = await run_server_cmd(
            populated_config,
            "update",
            "calc",
            "--source",
            "https://example.com/v2",
            "--notes",
            "new notes",
            "--env",
            "A=1",
            "B=2",
        )
        assert result == 0

        server = load_servers(populated_config)["calc"]
        assert server.source == "https://example.com/v2"
        assert server.notes == "new notes"
        assert server.env == {"A": "1", "B": "2"}
        # Untouched fields preserved
        assert server.command == "npx"
        assert server.prefix == "calc"

        captured = capsys.readouterr()
        assert "Updated server 'calc'" in captured.err

    @pytest.mark.asyncio
    async def test_update_command_resplits_args(self, populated_config):
        result = await run_server_cmd(populated_config, "update", "calc", "--command", "uvx some-mcp --flag")
        assert result == 0

        server = load_servers(populated_config)["calc"]
        assert server.command == "uvx"
        assert server.args == ["some-mcp", "--flag"]

    @pytest.mark.asyncio
    async def test_update_clear_fields(self, populated_config):
        result = await run_server_cmd(
            populated_config,
            "update",
            "calc",
            "--notes",
            "",
            "--prefix",
            "",
            "--env",
        )
        assert result == 0

        server = load_servers(populated_config)["calc"]
        assert server.notes is None
        assert server.prefix is None
        assert server.env is None
        # Command untouched
        assert server.command == "npx"

    @pytest.mark.asyncio
    async def test_update_enable_disable(self, populated_config):
        assert await run_server_cmd(populated_config, "update", "calc", "--disable") == 0
        assert load_servers(populated_config)["calc"].enabled is False

        assert await run_server_cmd(populated_config, "update", "calc", "--enable") == 0
        assert load_servers(populated_config)["calc"].enabled is True

    @pytest.mark.asyncio
    async def test_update_transport(self, populated_config):
        assert await run_server_cmd(populated_config, "update", "calc", "--transport", '{"keep_alive": false}') == 0
        assert load_servers(populated_config)["calc"].transport == {"keep_alive": False}

        assert await run_server_cmd(populated_config, "update", "calc", "--transport", "") == 0
        assert load_servers(populated_config)["calc"].transport is None

    @pytest.mark.asyncio
    async def test_update_invalid_prefix_rejected(self, populated_config, capsys):
        result = await run_server_cmd(populated_config, "update", "calc", "--prefix", "bad_prefix")
        assert result == 1
        # Config on disk unchanged
        assert load_servers(populated_config)["calc"].prefix == "calc"

        captured = capsys.readouterr()
        assert "Invalid server configuration" in captured.err

    @pytest.mark.asyncio
    async def test_update_unknown_server(self, config_path, capsys):
        result = await run_server_cmd(config_path, "update", "nope", "--notes", "x")
        assert result == 1

        captured = capsys.readouterr()
        assert "Server 'nope' not found" in captured.err

    @pytest.mark.asyncio
    async def test_update_no_options(self, populated_config, capsys):
        result = await run_server_cmd(populated_config, "update", "calc")
        assert result == 1

        captured = capsys.readouterr()
        assert "No updates specified" in captured.err

    @pytest.mark.asyncio
    async def test_update_invalid_env(self, populated_config, capsys):
        result = await run_server_cmd(populated_config, "update", "calc", "--env", "NOEQUALS")
        assert result == 1

        captured = capsys.readouterr()
        assert "Invalid environment variable format" in captured.err

    @pytest.mark.asyncio
    async def test_update_refuses_clearing_command_without_uri(self, populated_config, capsys):
        """Clearing the command with no URI set would leave the server unrunnable."""
        result = await run_server_cmd(populated_config, "update", "calc", "--command", "")
        assert result == 1
        assert load_servers(populated_config)["calc"].command == "npx"

        captured = capsys.readouterr()
        assert "Cannot clear both command and URI" in captured.err

    @pytest.mark.asyncio
    async def test_update_clear_command_with_uri_replacement(self, populated_config):
        """Switching from stdio to HTTP in one command works."""
        result = await run_server_cmd(
            populated_config, "update", "calc", "--command", "", "--uri", "http://localhost:9000/mcp"
        )
        assert result == 0

        server = load_servers(populated_config)["calc"]
        assert server.command is None
        assert server.uri == "http://localhost:9000/mcp"

    @pytest.mark.asyncio
    async def test_update_whitespace_command_treated_as_clear(self, populated_config, capsys):
        """A whitespace-only command must not crash; it parses to no command at all."""
        result = await run_server_cmd(populated_config, "update", "calc", "--command", "   ")
        assert result == 1

        captured = capsys.readouterr()
        assert "Cannot clear both command and URI" in captured.err

    @pytest.mark.asyncio
    async def test_update_unbalanced_quotes_rejected(self, populated_config, capsys):
        result = await run_server_cmd(populated_config, "update", "calc", "--command", 'echo "unclosed')
        assert result == 1
        assert load_servers(populated_config)["calc"].command == "npx"

        captured = capsys.readouterr()
        assert "Invalid command" in captured.err


class TestServerJSONOutput:
    """Test machine-readable output for server list/info."""

    @pytest.mark.asyncio
    async def test_list_json(self, config_path, capsys):
        await run_server_cmd(
            config_path,
            "add",
            "calc",
            "https://example.com/calc",
            "--command",
            "npx calculator-mcp",
            "--disable",
        )
        capsys.readouterr()

        result = await run_server_cmd(config_path, "list", "--json")
        assert result == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["servers"]["calc"]["source"] == "https://example.com/calc"
        assert data["servers"]["calc"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_info_json(self, config_path, capsys):
        await run_server_cmd(config_path, "add", "calc", "https://example.com/calc", "--env", "A=1")
        capsys.readouterr()

        result = await run_server_cmd(config_path, "info", "calc", "--json")
        assert result == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["calc"]["env"] == {"A": "1"}
        assert data["calc"]["enabled"] is True

    @pytest.mark.asyncio
    async def test_list_json_empty(self, config_path, capsys):
        result = await run_server_cmd(config_path, "list", "--json")
        assert result == 0

        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"servers": {}}
