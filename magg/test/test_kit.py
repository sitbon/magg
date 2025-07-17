"""Tests for kit functionality."""

import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from magg.kit import KitConfig, KitManager
from magg.settings import ConfigManager, MaggConfig, ServerConfig


class TestKitConfig:
    """Test KitConfig model."""

    def test_kit_config_basic(self):
        """Test basic kit configuration."""
        kit = KitConfig(
            name="test-kit",
            description="Test kit for unit tests",
            author="Test Author",
            version="1.0.0",
            keywords=["test", "example"],
            links={"homepage": "https://example.com"},
            servers={
                "test-server": ServerConfig(
                    name="test-server",
                    source="https://example.com/server",
                    command="python",
                    args=["-m", "test_server"]
                )
            }
        )

        assert kit.name == "test-kit"
        assert kit.description == "Test kit for unit tests"
        assert kit.author == "Test Author"
        assert kit.version == "1.0.0"
        assert "test" in kit.keywords
        assert kit.links["homepage"] == "https://example.com"
        assert "test-server" in kit.servers
        assert kit.servers["test-server"].command == "python"

    def test_kit_config_from_dict(self):
        """Test kit configuration from dictionary."""
        data = {
            "name": "calc-kit",
            "description": "Calculator kit",
            "servers": {
                "calc": {
                    "source": "https://github.com/example/calc",
                    "command": "node",
                    "args": ["calc.js"],
                    "enabled": False
                }
            }
        }

        kit = KitConfig(**data)
        assert kit.name == "calc-kit"
        assert kit.description == "Calculator kit"
        assert "calc" in kit.servers
        assert kit.servers["calc"].name == "calc"
        assert kit.servers["calc"].enabled is False

    def test_kit_config_server_validation(self):
        """Test that invalid servers are skipped with logging."""
        data = {
            "name": "test-kit",
            "description": "Test",
            "servers": {
                "valid": {
                    "source": "https://example.com/valid",
                    "command": "python"
                },
                "invalid": {
                    # Missing required 'source' field
                    "command": "python"
                }
            }
        }

        kit = KitConfig(**data)
        assert len(kit.servers) == 1
        assert "valid" in kit.servers
        assert "invalid" not in kit.servers

    def test_kit_config_strips_kits_field(self):
        """Test that 'kits' field is stripped from server definitions."""
        data = {
            "name": "test-kit",
            "description": "Test kit",
            "servers": {
                "server1": {
                    "source": "https://example.com/server1",
                    "command": "python",
                    "kits": ["should-be-removed"]  # This should be stripped
                },
                "server2": {
                    "source": "https://example.com/server2",
                    "uri": "http://localhost:8080",
                    "kits": ["also-removed", "multiple-items"]  # This should also be stripped
                }
            }
        }

        kit = KitConfig(**data)

        # Verify servers were created
        assert len(kit.servers) == 2
        assert "server1" in kit.servers
        assert "server2" in kit.servers

        # Verify 'kits' field was not included in the server configs
        # The ServerConfig model has a default empty list for kits
        assert kit.servers["server1"].kits == []
        assert kit.servers["server2"].kits == []


class TestKitManager:
    """Test KitManager functionality."""

    def test_magg_path_integration(self, tmp_path):
        """Test that MAGG_PATH environment variable works with kit manager."""
        # Create some test directories
        custom_dir = tmp_path / "custom"
        custom_kitd = custom_dir / "kit.d"
        custom_kitd.mkdir(parents=True)

        another_dir = tmp_path / "another"
        another_kitd = another_dir / "kit.d"
        another_kitd.mkdir(parents=True)

        # Test with MAGG_PATH environment variable
        env_path = f"{custom_dir}:{another_dir}"
        with patch.dict(os.environ, {"MAGG_PATH": env_path}):
            config_manager = ConfigManager()
            kit_manager = KitManager(config_manager)

            # Should find kit.d directories from MAGG_PATH
            kitd_paths_str = [str(p) for p in kit_manager.kitd_paths]
            assert str(custom_kitd) in kitd_paths_str
            assert str(another_kitd) in kitd_paths_str

    def test_discover_kits(self, tmp_path):
        """Test kit discovery in directories."""
        # Create kit.d directory with some kit files
        kitd_path = tmp_path / "kit.d"
        kitd_path.mkdir()

        # Create valid kit files
        kit1_path = kitd_path / "kit1.json"
        kit1_path.write_text(json.dumps({
            "name": "kit1",
            "description": "First kit",
            "servers": {}
        }))

        kit2_path = kitd_path / "kit2.json"
        kit2_path.write_text(json.dumps({
            "name": "kit2",
            "description": "Second kit",
            "servers": {}
        }))

        # Create non-kit file (should be ignored)
        other_path = kitd_path / "readme.txt"
        other_path.write_text("This is not a kit")

        # Test discovery
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        manager = KitManager(config_manager, [kitd_path])
        kits = manager.discover_kits()

        assert len(kits) == 2
        assert "kit1" in kits
        assert "kit2" in kits
        assert kits["kit1"] == kit1_path
        assert kits["kit2"] == kit2_path

    def test_discover_kits_duplicate_names(self, tmp_path):
        """Test handling of duplicate kit names across directories."""
        # Create two kit.d directories
        kitd1 = tmp_path / "kit.d1"
        kitd2 = tmp_path / "kit.d2"
        kitd1.mkdir()
        kitd2.mkdir()

        # Create kit with same name in both directories
        kit1_path = kitd1 / "mykit.json"
        kit1_path.write_text(json.dumps({"name": "mykit", "servers": {}}))

        kit2_path = kitd2 / "mykit.json"
        kit2_path.write_text(json.dumps({"name": "mykit", "servers": {}}))

        # Test discovery - first one wins
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        manager = KitManager(config_manager, [kitd1, kitd2])
        kits = manager.discover_kits()

        assert len(kits) == 1
        assert kits["mykit"] == kit1_path  # First one found

    def test_load_kit_success(self, tmp_path):
        """Test successful kit loading."""
        kit_path = tmp_path / "test.json"
        kit_data = {
            "name": "test-kit",
            "description": "Test kit",
            "author": "Tester",
            "servers": {
                "server1": {
                    "source": "https://example.com/1",
                    "command": "python"
                }
            }
        }
        kit_path.write_text(json.dumps(kit_data))

        config_manager = ConfigManager(str(tmp_path / "config.json"))
        manager = KitManager(config_manager)
        kit = manager.load_kit(kit_path)

        assert kit is not None
        assert kit.name == "test-kit"
        assert kit.description == "Test kit"
        assert kit.author == "Tester"
        assert "server1" in kit.servers

    def test_load_kit_invalid_json(self, tmp_path):
        """Test loading kit with invalid JSON."""
        kit_path = tmp_path / "invalid.json"
        kit_path.write_text("{ invalid json }")

        config_manager = ConfigManager(str(tmp_path / "config.json"))
        manager = KitManager(config_manager)
        kit = manager.load_kit(kit_path)

        assert kit is None

    def test_load_kit_missing_name(self, tmp_path):
        """Test loading kit without name uses filename."""
        kit_path = tmp_path / "unnamed.json"
        kit_data = {
            "description": "Kit without explicit name",
            "servers": {}
        }
        kit_path.write_text(json.dumps(kit_data))

        config_manager = ConfigManager(str(tmp_path / "config.json"))
        manager = KitManager(config_manager)
        kit = manager.load_kit(kit_path)

        assert kit is not None
        assert kit.name == "unnamed"  # Uses filename stem

    def test_kit_manager_operations(self, tmp_path):
        """Test kit manager add/remove/get operations."""
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        manager = KitManager(config_manager)

        kit1 = KitConfig(name="kit1", description="First kit", servers={})
        kit2 = KitConfig(name="kit2", description="Second kit", servers={})

        # Add kits
        assert manager.add_kit("kit1", kit1) is True
        assert manager.add_kit("kit2", kit2) is True
        assert manager.add_kit("kit1", kit1) is False  # Already exists

        # Get loaded kits
        loaded = manager.kits
        assert len(loaded) == 2
        assert "kit1" in loaded
        assert "kit2" in loaded

        # Get kit servers
        servers = manager.get_kit_servers("kit1")
        assert servers == {}  # Empty servers dict

        servers = manager.get_kit_servers("nonexistent")
        assert servers == {}

        # Remove kit
        assert manager.remove_kit("kit1") is True
        assert manager.remove_kit("kit1") is False  # Already removed

        loaded = manager.kits
        assert len(loaded) == 1
        assert "kit2" in loaded

    def test_get_all_servers(self, tmp_path):
        """Test getting all servers from all kits."""
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        manager = KitManager(config_manager)

        # Create kits with overlapping servers
        kit1 = KitConfig(
            name="kit1",
            description="Kit 1",
            servers={
                "server-a": ServerConfig(name="server-a", source="https://a.com"),
                "server-b": ServerConfig(name="server-b", source="https://b.com")
            }
        )

        kit2 = KitConfig(
            name="kit2",
            description="Kit 2",
            servers={
                "server-b": ServerConfig(name="server-b", source="https://b.com"),
                "server-c": ServerConfig(name="server-c", source="https://c.com")
            }
        )

        manager.add_kit("kit1", kit1)
        manager.add_kit("kit2", kit2)

        all_servers = manager.get_all_servers()

        assert len(all_servers) == 3
        assert "server-a" in all_servers
        assert "server-b" in all_servers
        assert "server-c" in all_servers

        # Check kit tracking
        _, kits_a = all_servers["server-a"]
        assert kits_a == ["kit1"]

        _, kits_b = all_servers["server-b"]
        assert set(kits_b) == {"kit1", "kit2"}  # In both kits

        _, kits_c = all_servers["server-c"]
        assert kits_c == ["kit2"]


class TestKitManagerIntegration:
    """Test kit manager integration with config management."""

    def test_load_kits_from_config(self, tmp_path):
        """Test loading kits listed in config."""
        # Create kit files
        kitd_path = tmp_path / "kit.d"
        kitd_path.mkdir()

        kit1_path = kitd_path / "kit1.json"
        kit1_path.write_text(json.dumps({
            "name": "kit1",
            "description": "Kit 1",
            "servers": {}
        }))

        kit2_path = kitd_path / "kit2.json"
        kit2_path.write_text(json.dumps({
            "name": "kit2",
            "description": "Kit 2",
            "servers": {}
        }))

        # Create kit manager with custom paths
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        kit_manager = KitManager(config_manager, [kitd_path])

        # Create config with kits
        from magg.settings import KitInfo
        config = MaggConfig()
        config.kits = {
            "kit1": KitInfo(name="kit1", source="file"),
            "kit2": KitInfo(name="kit2", source="file"),
            "nonexistent": KitInfo(name="nonexistent", source="file")
        }

        # Load kits
        kit_manager.load_kits_from_config(config)

        # Check loaded kits
        loaded = kit_manager.kits
        assert len(loaded) == 3  # Now includes the nonexistent kit
        assert "kit1" in loaded
        assert "kit2" in loaded
        assert "nonexistent" in loaded  # Now created in memory

        # Verify the in-memory created kit has minimal config
        assert loaded["nonexistent"].name == "nonexistent"
        assert loaded["nonexistent"].description == ""
        assert loaded["nonexistent"].servers == {}

    def test_load_kit_new_servers(self, tmp_path):
        """Test loading a kit with new servers."""
        # Create kit file
        kitd_path = tmp_path / "kit.d"
        kitd_path.mkdir()

        kit_path = kitd_path / "web-kit.json"
        kit_path.write_text(json.dumps({
            "name": "web-kit",
            "description": "Web tools",
            "servers": {
                "browser": {
                    "source": "https://browser.com",
                    "command": "node",
                    "args": ["browser.js"]
                },
                "scraper": {
                    "source": "https://scraper.com",
                    "uri": "http://localhost:8080"
                }
            }
        }))

        # Create kit manager with custom paths
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        kit_manager = KitManager(config_manager, [kitd_path])

        # Create config
        config = MaggConfig()

        # Load kit
        success, message = kit_manager.load_kit_to_config("web-kit", config)

        assert success is True
        assert "web-kit" in config.kits
        assert "browser" in config.servers
        assert "scraper" in config.servers
        assert config.servers["browser"].kits == ["web-kit"]
        assert config.servers["scraper"].kits == ["web-kit"]
        assert "Added servers: browser, scraper" in message

    def test_load_kit_existing_servers(self, tmp_path):
        """Test loading a kit with servers that already exist."""
        # Create kit file
        kitd_path = tmp_path / "kit.d"
        kitd_path.mkdir()

        kit_path = kitd_path / "kit1.json"
        kit_path.write_text(json.dumps({
            "name": "kit1",
            "description": "Kit 1",
            "servers": {
                "shared-server": {
                    "source": "https://shared.com",
                    "command": "python"
                }
            }
        }))

        # Create kit manager with custom paths
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        kit_manager = KitManager(config_manager, [kitd_path])

        # Create config with existing server
        config = MaggConfig()
        existing_server = ServerConfig(
            name="shared-server",
            source="https://shared.com",
            command="python",
            kits=["other-kit"]
        )
        config.servers["shared-server"] = existing_server

        # Load kit
        success, message = kit_manager.load_kit_to_config("kit1", config)

        assert success is True
        assert "kit1" in config.kits
        assert config.servers["shared-server"].kits == ["other-kit", "kit1"]
        assert "Updated servers: shared-server" in message

    def test_load_kit_already_loaded(self, tmp_path):
        """Test loading a kit that's already loaded."""
        from magg.settings import KitInfo
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        kit_manager = KitManager(config_manager)

        config = MaggConfig()
        config.kits = {"existing-kit": KitInfo(name="existing-kit", source="file")}

        success, message = kit_manager.load_kit_to_config("existing-kit", config)

        assert success is False
        assert "already loaded" in message

    def test_unload_kit_exclusive_servers(self, tmp_path):
        """Test unloading a kit removes servers only in that kit."""
        from magg.settings import KitInfo
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        kit_manager = KitManager(config_manager)

        # Setup config with servers
        config = MaggConfig()
        config.kits = {"kit1": KitInfo(name="kit1", source="file")}

        server1 = ServerConfig(
            name="exclusive-server",
            source="https://exclusive.com",
            kits=["kit1"]
        )
        server2 = ServerConfig(
            name="shared-server",
            source="https://shared.com",
            kits=["kit1", "kit2"]
        )

        config.servers["exclusive-server"] = server1
        config.servers["shared-server"] = server2

        # Add kit to manager
        kit = KitConfig(name="kit1", description="Kit 1", servers={})
        kit_manager.add_kit("kit1", kit)

        # Unload kit
        success, message = kit_manager.unload_kit_from_config("kit1", config)

        assert success is True
        assert "kit1" not in config.kits
        assert "exclusive-server" not in config.servers
        assert "shared-server" in config.servers
        assert config.servers["shared-server"].kits == ["kit2"]
        assert "Removed servers: exclusive-server" in message
        assert "Updated servers: shared-server" in message

    def test_unload_kit_not_loaded(self, tmp_path):
        """Test unloading a kit that's not loaded."""
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        kit_manager = KitManager(config_manager)

        config = MaggConfig()

        success, message = kit_manager.unload_kit_from_config("nonexistent", config)

        assert success is False
        assert "not loaded" in message

    def test_list_kits(self, tmp_path):
        """Test listing all kits with status."""
        # Create kit files
        kitd_path = tmp_path / "kit.d"
        kitd_path.mkdir()

        kit1_path = kitd_path / "loaded-kit.json"
        kit1_path.write_text(json.dumps({
            "name": "loaded-kit",
            "description": "A loaded kit",
            "author": "Author 1",
            "version": "1.0.0",
            "keywords": ["test"],
            "servers": {"s1": {"source": "https://s1.com"}}
        }))

        kit2_path = kitd_path / "available-kit.json"
        kit2_path.write_text(json.dumps({
            "name": "available-kit",
            "description": "An available kit",
            "author": "Author 2",
            "version": "2.0.0",
            "keywords": ["example"],
            "servers": {"s2": {"source": "https://s2.com"}}
        }))

        # Create kit manager with custom paths
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        kit_manager = KitManager(config_manager, [kitd_path])

        # Load one kit
        kit = kit_manager.load_kit(kit1_path)
        kit_manager.add_kit("loaded-kit", kit)

        # List kits
        kits = kit_manager.list_all_kits()

        assert len(kits) == 2

        assert kits["loaded-kit"]["loaded"] is True
        assert kits["loaded-kit"]["description"] == "A loaded kit"
        assert kits["loaded-kit"]["author"] == "Author 1"
        assert kits["loaded-kit"]["servers"] == ["s1"]

        assert kits["available-kit"]["loaded"] is False
        assert kits["available-kit"]["description"] == "An available kit"
        assert kits["available-kit"]["author"] == "Author 2"
        assert kits["available-kit"]["servers"] == ["s2"]

    def test_get_kit_info(self, tmp_path):
        """Test getting detailed kit information."""
        # Create kit file
        kitd_path = tmp_path / "kit.d"
        kitd_path.mkdir()

        kit_path = kitd_path / "info-kit.json"
        kit_data = {
            "name": "info-kit",
            "description": "Kit for info test",
            "author": "Info Author",
            "version": "3.0.0",
            "keywords": ["info", "test"],
            "links": {
                "homepage": "https://info.com",
                "docs": "https://info.com/docs"
            },
            "servers": {
                "info-server": {
                    "source": "https://info-server.com",
                    "command": "python",
                    "args": ["-m", "info_server"],
                    "notes": "Info server for testing"
                }
            }
        }
        kit_path.write_text(json.dumps(kit_data))

        # Create kit manager with custom paths
        config_manager = ConfigManager(str(tmp_path / "config.json"))
        kit_manager = KitManager(config_manager, [kitd_path])

        # Get info for available kit
        info = kit_manager.get_kit_details("info-kit")

        assert info is not None
        assert info["loaded"] is False
        assert info["name"] == "info-kit"
        assert info["description"] == "Kit for info test"
        assert info["author"] == "Info Author"
        assert info["version"] == "3.0.0"
        assert info["keywords"] == ["info", "test"]
        assert info["links"]["homepage"] == "https://info.com"
        assert "info-server" in info["servers"]
        assert info["servers"]["info-server"]["command"] == "python"

        # Test nonexistent kit
        info = kit_manager.get_kit_details("nonexistent")
        assert info is None


class TestKitConfigPersistence:
    """Test that kit information is properly saved and loaded from config."""

    def test_config_saves_kits_field(self, tmp_path):
        """Test that config saves and loads the kits field."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(str(config_path))

        # Create config with kits
        config = MaggConfig()
        from magg.settings import KitInfo
        config.kits = {
            "kit1": KitInfo(name="kit1", source="file"),
            "kit2": KitInfo(name="kit2", source="file")
        }

        # Add a server with kit tracking
        server = ServerConfig(
            name="test-server",
            source="https://test.com",
            kits=["kit1"]
        )
        config.servers["test-server"] = server

        # Save config
        manager.save_config(config)

        # Load and verify
        loaded = manager.load_config()
        assert "kit1" in loaded.kits
        assert "kit2" in loaded.kits
        assert loaded.kits["kit1"].name == "kit1"
        assert loaded.kits["kit1"].source == "file"
        assert loaded.kits["kit2"].name == "kit2"
        assert loaded.kits["kit2"].source == "file"
        assert loaded.servers["test-server"].kits == ["kit1"]

        # Check raw JSON
        with open(config_path) as f:
            data = json.load(f)

        assert "kit1" in data["kits"]
        assert "kit2" in data["kits"]
        assert data["kits"]["kit1"]["name"] == "kit1"
        assert data["kits"]["kit1"]["source"] == "file"
        assert data["servers"]["test-server"]["kits"] == ["kit1"]

    def test_config_without_kits_field(self, tmp_path):
        """Test loading config without kits field (backward compatibility)."""
        config_path = tmp_path / "config.json"

        # Create old-style config without kits
        old_config = {
            "servers": {
                "server1": {
                    "source": "https://server1.com",
                    "command": "python"
                }
            }
        }

        with open(config_path, "w") as f:
            json.dump(old_config, f)

        # Load config
        manager = ConfigManager(str(config_path))
        config = manager.load_config()

        # Should have empty kits dict
        assert config.kits == {}
        assert "server1" in config.servers
        assert config.servers["server1"].kits == []  # Default empty list
