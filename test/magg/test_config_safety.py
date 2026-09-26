"""Tests that saving the config never loses data the user wrote."""

import asyncio
import json
import os
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from magg import reload as reload_module
from magg.kit import KitManager
from magg.reload import ConfigReloader
from magg.settings import BearerAuthConfig, ConfigFileError, ConfigManager, ServerConfig


@pytest.fixture
def config_path(tmp_path):
    return tmp_path / "config.json"


def write_config(path, data):
    path.write_text(json.dumps(data, indent=2))


def read_config(path):
    return json.loads(path.read_text())


def replace_config(path, data):
    """Write the config the way many editors and tools do: a new file renamed over the old one."""
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(data))
    os.replace(tmp_path, path)


async def wait_until(predicate, timeout=5.0):
    """Poll until predicate() is true, returning whether it became true in time."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.05)
    return True


def server_names(change):
    return {server_change.name for server_change in change.server_changes}


class TestEnvironmentIsolation:
    """Nested config models must not read unrelated environment variables."""

    def test_server_config_ignores_env(self, monkeypatch):
        # Termux sets PREFIX=/usr, POSIX shells use ENV, and URI/ENABLED are common names
        monkeypatch.setenv("PREFIX", "/usr")
        monkeypatch.setenv("URI", "http://evil.example/mcp")
        monkeypatch.setenv("ENABLED", "false")
        monkeypatch.setenv("ENV", "/home/user/.shrc")

        server = ServerConfig.model_validate({"name": "calc", "source": "https://x", "command": "echo"})

        assert server.prefix is None
        assert server.uri is None
        assert server.enabled is True
        assert server.env is None

    def test_bearer_auth_config_ignores_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AUDIENCE", "other")
        monkeypatch.setenv("KEY_PATH", str(tmp_path))

        config = BearerAuthConfig()

        assert config.audience == "magg"
        assert config.key_path == Path.home() / ".ssh" / "magg"


class TestSaveConfig:
    """ConfigManager.save_config preserves what it didn't load."""

    def test_refuses_to_overwrite_unparseable_file(self, config_path):
        original = '{"servers": {"a": {"source": "s", "command": "echo"}},}'
        config_path.write_text(original)
        manager = ConfigManager(str(config_path))

        config = manager.load_config()
        assert config.servers == {}

        config.add_server(ServerConfig(name="b", source="s", command="echo"))
        assert manager.save_config(config) is False
        assert config_path.read_text() == original

    def test_read_config_raises_on_unparseable_file(self, config_path):
        config_path.write_text("[1, 2, 3]")

        with pytest.raises(ConfigFileError):
            ConfigManager(str(config_path)).read_config()

    def test_empty_file_is_treated_as_new(self, config_path):
        config_path.write_text("")
        manager = ConfigManager(str(config_path))

        config = manager.load_config()
        config.add_server(ServerConfig(name="a", source="s", command="echo"))

        assert manager.save_config(config) is True
        assert list(read_config(config_path)["servers"]) == ["a"]

    def test_invalid_server_is_kept(self, config_path):
        write_config(
            config_path,
            {
                "servers": {
                    "good": {"source": "s", "command": "echo"},
                    "bad": {"source": "s", "command": "echo", "prefix": "not-valid!"},
                }
            },
        )
        manager = ConfigManager(str(config_path))

        config = manager.load_config()
        assert list(config.servers) == ["good"]

        config.add_server(ServerConfig(name="new", source="s", command="echo"))
        assert manager.save_config(config) is True

        servers = read_config(config_path)["servers"]
        assert set(servers) == {"good", "bad", "new"}
        assert servers["bad"]["prefix"] == "not-valid!"

    def test_removed_server_is_removed(self, config_path):
        write_config(
            config_path,
            {"servers": {"a": {"source": "s", "command": "echo"}, "b": {"source": "s", "command": "echo"}}},
        )
        manager = ConfigManager(str(config_path))

        config = manager.load_config()
        config.remove_server("a")
        assert manager.save_config(config) is True

        assert list(read_config(config_path)["servers"]) == ["b"]

    def test_top_level_settings_are_kept(self, config_path):
        write_config(
            config_path,
            {"self_prefix": "hub", "servers": {"a": {"source": "s", "command": "echo"}}, "custom": {"x": 1}},
        )
        manager = ConfigManager(str(config_path))

        config = manager.load_config()
        assert config.self_prefix == "hub"

        config.remove_server("a")
        assert manager.save_config(config) is True

        data = read_config(config_path)
        assert list(data) == ["self_prefix", "servers", "custom"]
        assert data["self_prefix"] == "hub"
        assert data["custom"] == {"x": 1}

    def test_invalid_setting_does_not_discard_later_settings(self, config_path):
        write_config(
            config_path,
            {"auto_reload": "maybe", "self_prefix": "hub", "servers": {"a": {"source": "s", "command": "echo"}}},
        )

        config = ConfigManager(str(config_path)).load_config()

        assert config.auto_reload is True  # Invalid value skipped, default kept
        assert config.self_prefix == "hub"
        assert list(config.servers) == ["a"]

    def test_write_preserves_mode_and_symlink(self, tmp_path):
        real_path = tmp_path / "real.json"
        write_config(real_path, {"servers": {}})
        os.chmod(real_path, 0o640)
        link_path = tmp_path / "config.json"
        link_path.symlink_to(real_path)
        manager = ConfigManager(str(link_path))

        config = manager.load_config()
        config.add_server(ServerConfig(name="a", source="s", command="echo"))
        assert manager.save_config(config) is True

        assert link_path.is_symlink()
        assert list(read_config(real_path)["servers"]) == ["a"]
        assert stat.S_IMODE(real_path.stat().st_mode) == 0o640
        assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json", "real.json"]

    @pytest.mark.asyncio
    async def test_kits_survive_save_with_reload_enabled(self, config_path):
        write_config(
            config_path,
            {
                "servers": {"calc": {"source": "s", "command": "echo", "enabled": False, "kits": ["mykit"]}},
                "kits": {"mykit": {"name": "mykit", "description": "d", "source": "file"}},
            },
        )
        manager = ConfigManager(str(config_path))

        async def callback(change):
            pass

        await manager.setup_config_reload(callback)
        try:
            await asyncio.sleep(0.1)  # Let the watcher load its baseline

            config = manager.load_config()
            assert list(config.kits) == ["mykit"]

            config.add_server(ServerConfig(name="other", source="s", command="echo", enabled=False))
            assert manager.save_config(config) is True
        finally:
            await manager.stop_config_reload()

        data = read_config(config_path)
        assert list(data["kits"]) == ["mykit"]
        assert set(data["servers"]) == {"calc", "other"}


class TestReload:
    """Config reload picks up real file changes, including ones made by rename."""

    @pytest.fixture
    def changes(self):
        return []

    @pytest.fixture
    def callback(self, changes):
        async def callback(change):
            changes.append(change)

        return callback

    @pytest.mark.asyncio
    async def test_rename_over_config_triggers_reload(self, config_path, changes, callback):
        write_config(config_path, {"servers": {}})
        reloader = ConfigReloader(config_path, callback)
        await reloader.start_watching(poll_interval=0.1)
        try:
            await asyncio.sleep(0.2)  # Let the watcher load its baseline

            replace_config(config_path, {"servers": {"a": {"source": "s", "command": "echo"}}})

            assert await wait_until(lambda: changes), "rename over the config was not detected"
            assert server_names(changes[0]) == {"a"}
        finally:
            await reloader.stop_watching()

    @pytest.mark.asyncio
    async def test_own_save_is_ignored_but_next_edit_is_not(self, config_path, changes, callback):
        write_config(config_path, {"servers": {}})
        manager = ConfigManager(str(config_path))
        await manager.setup_config_reload(callback)
        try:
            await asyncio.sleep(0.2)

            # Magg's own save replaces the file too, and must not echo back as a reload
            config = manager.load_config()
            config.add_server(ServerConfig(name="saved", source="s", command="echo"))
            assert manager.save_config(config) is True
            await asyncio.sleep(0.5)
            assert changes == []

            # The ignore must be used up by that save, so the next outside edit still reloads
            data = read_config(config_path)
            data["servers"]["edited"] = {"source": "s", "command": "echo"}
            replace_config(config_path, data)

            assert await wait_until(lambda: changes), "edit after an internal save was not detected"
            assert server_names(changes[0]) == {"edited"}
        finally:
            await manager.stop_config_reload()

    @pytest.mark.asyncio
    async def test_polling_when_watchdog_disabled(self, config_path, changes, callback, monkeypatch):
        observer = MagicMock()
        monkeypatch.setattr(reload_module, "Observer", observer)
        write_config(config_path, {"servers": {}})
        reloader = ConfigReloader(config_path, callback)
        await reloader.start_watching(poll_interval=0.1, use_watchdog=False)
        try:
            await asyncio.sleep(0.2)
            write_config(config_path, {"servers": {"a": {"source": "s", "command": "echo"}}})
            # Polling compares mtimes, so make sure it moves even on coarse-grained filesystems
            os.utime(config_path, (config_path.stat().st_atime, config_path.stat().st_mtime + 1))

            assert await wait_until(lambda: changes), "polling did not detect the change"
        finally:
            await reloader.stop_watching()

        observer.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_placeholder_does_not_block_reload(self, config_path, changes, callback):
        write_config(config_path, {"servers": {}})
        reloader = ConfigReloader(config_path, callback)
        await reloader.reload_config()  # Establish the baseline

        write_config(
            config_path,
            {
                "servers": {
                    "placeholder": {"source": "s", "enabled": False},
                    "real": {"source": "s", "command": "echo"},
                }
            },
        )
        assert await reloader.reload_config() is not None

        assert server_names(changes[-1]) == {"placeholder", "real"}

    @pytest.mark.asyncio
    async def test_unparseable_file_is_not_applied(self, config_path, changes, callback):
        write_config(config_path, {"servers": {"a": {"source": "s", "command": "echo"}}})
        reloader = ConfigReloader(config_path, callback)
        await reloader.reload_config()  # Establish the baseline
        changes.clear()

        # A half-written or mistyped file must not look like "every server was removed"
        config_path.write_text('{"servers": {')
        assert await reloader.reload_config() is None
        assert changes == []


class TestKitDiscovery:
    """Kits next to an explicitly configured config file are found."""

    def test_kitd_next_to_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAGG_PATH", str(tmp_path / "elsewhere"))
        config_dir = tmp_path / "project"
        (config_dir / "kit.d").mkdir(parents=True)
        (config_dir / "kit.d" / "local.json").write_text(json.dumps({"name": "local", "servers": {}}))

        kit_manager = KitManager(ConfigManager(str(config_dir / "config.json")))

        assert "local" in kit_manager.discover_kits()
