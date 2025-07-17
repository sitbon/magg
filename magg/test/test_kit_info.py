"""Tests for KitInfo model and kit metadata functionality."""

import json
import pytest
import tempfile
from pathlib import Path

from magg.settings import KitInfo, MaggConfig, ConfigManager


class TestKitInfo:
    """Test KitInfo model."""

    def test_kit_info_creation(self):
        """Test creating KitInfo with all fields."""
        kit_info = KitInfo(
            name="test-kit",
            description="Test kit description",
            path="/path/to/kit.json",
            source="file"
        )

        assert kit_info.name == "test-kit"
        assert kit_info.description == "Test kit description"
        assert kit_info.path == "/path/to/kit.json"
        assert kit_info.source == "file"

    def test_kit_info_minimal(self):
        """Test creating KitInfo with only required fields."""
        kit_info = KitInfo(name="minimal-kit")

        assert kit_info.name == "minimal-kit"
        assert kit_info.description is None
        assert kit_info.path is None
        assert kit_info.source is None

    def test_kit_info_inline_source(self):
        """Test creating KitInfo for inline kit (no file)."""
        kit_info = KitInfo(
            name="inline-kit",
            description="Kit created programmatically",
            source="inline"
        )

        assert kit_info.name == "inline-kit"
        assert kit_info.description == "Kit created programmatically"
        assert kit_info.path is None
        assert kit_info.source == "inline"


class TestKitInfoPersistence:
    """Test saving and loading kit metadata."""

    def test_save_load_kit_info(self, tmp_path):
        """Test saving and loading config with KitInfo."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(str(config_path))

        # Create config with kit metadata
        config = MaggConfig()
        config.kits["file-kit"] = KitInfo(
            name="file-kit",
            description="Kit from file",
            path="/path/to/file-kit.json",
            source="file"
        )
        config.kits["inline-kit"] = KitInfo(
            name="inline-kit",
            description="Programmatic kit",
            source="inline"
        )

        # Save config
        assert manager.save_config(config) is True

        # Verify JSON structure
        with open(config_path) as f:
            data = json.load(f)

        assert "kits" in data
        assert "file-kit" in data["kits"]
        assert data["kits"]["file-kit"]["name"] == "file-kit"
        assert data["kits"]["file-kit"]["description"] == "Kit from file"
        assert data["kits"]["file-kit"]["path"] == "/path/to/file-kit.json"
        assert data["kits"]["file-kit"]["source"] == "file"

        assert "inline-kit" in data["kits"]
        assert data["kits"]["inline-kit"]["name"] == "inline-kit"
        assert data["kits"]["inline-kit"]["description"] == "Programmatic kit"
        assert "path" not in data["kits"]["inline-kit"]  # None values excluded
        assert data["kits"]["inline-kit"]["source"] == "inline"

        # Load config back
        loaded = manager.load_config()

        assert len(loaded.kits) == 2
        assert loaded.kits["file-kit"].name == "file-kit"
        assert loaded.kits["file-kit"].description == "Kit from file"
        assert loaded.kits["file-kit"].path == "/path/to/file-kit.json"
        assert loaded.kits["file-kit"].source == "file"

        assert loaded.kits["inline-kit"].name == "inline-kit"
        assert loaded.kits["inline-kit"].description == "Programmatic kit"
        assert loaded.kits["inline-kit"].path is None
        assert loaded.kits["inline-kit"].source == "inline"

    def test_backward_compatibility(self, tmp_path):
        """Test loading old format (list of kit names) converts to new format."""
        config_path = tmp_path / "config.json"

        # Create old-style config
        old_config = {
            "servers": {},
            "kits": ["kit1", "kit2", "kit3"]
        }

        with open(config_path, "w") as f:
            json.dump(old_config, f)

        # Load config
        manager = ConfigManager(str(config_path))
        config = manager.load_config()

        # Should convert to new format
        assert isinstance(config.kits, dict)
        assert len(config.kits) == 3
        assert "kit1" in config.kits
        assert "kit2" in config.kits
        assert "kit3" in config.kits

        # Check converted kit info
        assert config.kits["kit1"].name == "kit1"
        assert config.kits["kit1"].source == "legacy"
        assert config.kits["kit1"].description is None
        assert config.kits["kit1"].path is None

    def test_kit_info_no_env_pollution(self):
        """Test that KitInfo doesn't pick up environment variables."""
        import os

        # Set some environment variables that might conflict
        old_path = os.environ.get("PATH")
        old_name = os.environ.get("NAME")

        try:
            os.environ["PATH"] = "/usr/bin:/bin"
            os.environ["NAME"] = "environment-name"

            # Create KitInfo - should not pick up env vars
            kit_info = KitInfo(
                name="test-kit",
                path="/path/to/kit.json"
            )

            assert kit_info.name == "test-kit"
            assert kit_info.path == "/path/to/kit.json"
            assert kit_info.path != "/usr/bin:/bin"

        finally:
            # Restore environment
            if old_path is not None:
                os.environ["PATH"] = old_path
            else:
                os.environ.pop("PATH", None)

            if old_name is not None:
                os.environ["NAME"] = old_name
            else:
                os.environ.pop("NAME", None)
