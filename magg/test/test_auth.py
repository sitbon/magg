"""Tests for Magg authentication."""
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from magg.auth import BearerAuthManager
from magg.settings import AuthConfig, BearerAuthConfig, ConfigManager
from fastmcp.server.auth import BearerAuthProvider


class TestBearerAuthConfig:
    """Test BearerAuthConfig model."""

    def test_defaults(self):
        """Test default values."""
        config = BearerAuthConfig()
        assert config.issuer == "https://magg.local"
        assert config.audience == "magg"
        assert config.key_path == Path.home() / ".ssh" / "magg"

    def test_model_dump_excludes_defaults(self):
        """Test that model_dump excludes default values."""
        config = BearerAuthConfig()
        data = config.model_dump(
            mode="json",
            exclude_unset=True,
            exclude_defaults=True,
            exclude_none=True
        )
        assert data == {}

    def test_model_dump_includes_custom(self):
        """Test that model_dump includes custom values."""
        config = BearerAuthConfig(issuer="https://example.com", audience="custom")
        data = config.model_dump(
            mode="json",
            exclude_unset=True,
            exclude_defaults=True,
            exclude_none=True
        )
        assert data == {
            "issuer": "https://example.com",
            "audience": "custom"
        }


class TestConfigManagerAuth:
    """Test ConfigManager auth functionality."""

    def test_load_auth_config_missing(self, tmp_path):
        """Test loading when auth.json doesn't exist."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(str(config_path))

        # No auth.json should return default config
        auth_config = manager.load_auth_config()
        assert auth_config is not None
        assert auth_config.bearer.issuer == "https://magg.local"
        assert auth_config.bearer.audience == "magg"

    def test_load_auth_config_with_default_key(self, tmp_path):
        """Test loading uses defaults when key exists but no auth.json."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(str(config_path))

        # Create a fake key file
        ssh_dir = Path.home() / '.ssh'
        key_path = ssh_dir / 'magg.key'

        with patch.object(Path, 'exists') as mock_exists:
            # First call checks auth.json (doesn't exist)
            # Second call checks key file (exists)
            mock_exists.side_effect = [False, True]

            auth_config = manager.load_auth_config()
            assert auth_config is not None
            assert auth_config.bearer.issuer == "https://magg.local"
            assert auth_config.bearer.audience == "magg"

    def test_save_load_auth_config(self, tmp_path):
        """Test saving and loading auth config."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(str(config_path))

        # Save custom config
        bearer_config = BearerAuthConfig(
            issuer="https://test.example.com",
            audience="test-app"
        )
        auth_config = AuthConfig(bearer=bearer_config)
        assert manager.save_auth_config(auth_config)

        # Verify file contents
        auth_path = tmp_path / "auth.json"
        with open(auth_path) as f:
            data = json.load(f)

        # Should have bearer nested structure with key_path
        assert data == {
            "bearer": {
                "issuer": "https://test.example.com",
                "audience": "test-app",
                "key_path": str(Path.home() / ".ssh" / "magg")
            }
        }

        # Load it back
        loaded = manager.load_auth_config()
        assert loaded is not None
        assert loaded.bearer.issuer == "https://test.example.com"
        assert loaded.bearer.audience == "test-app"


class TestBearerAuthManager:
    """Test AuthManager functionality."""

    def test_not_enabled_without_keys(self):
        """Test auth is disabled without keys."""
        config = BearerAuthConfig(key_path=Path("/nonexistent"))
        manager = BearerAuthManager(config)
        assert not manager.enabled
        with pytest.raises(RuntimeError, match="Authentication is not enabled"):
            manager.load_keys()

    def test_enabled_with_keys(self, tmp_path):
        """Test auth is enabled when keys exist."""
        # Create a temporary key
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        private_key_path = key_dir / "test.key"

        # Generate a test key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        private_key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )

        config = BearerAuthConfig(key_path=key_dir, audience="test")
        manager = BearerAuthManager(config)
        assert manager.enabled

    @patch.dict('os.environ', {'MAGG_PRIVATE_KEY': ''})
    def test_load_private_key_from_env(self):
        """Test loading private key from environment variable."""
        # Generate a test key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        config = BearerAuthConfig()
        manager = BearerAuthManager(config)

        with patch.dict('os.environ', {'MAGG_PRIVATE_KEY': pem}):
            loaded_key = manager._load_private_key()
            assert loaded_key is not None
            # Verify it's the same key by comparing public keys
            assert loaded_key.public_key().public_numbers() == private_key.public_key().public_numbers()

    def test_generate_keypair(self, tmp_path):
        """Test keypair generation."""
        # Use a temporary directory for SSH keys
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        config = BearerAuthConfig(audience="test", key_path=ssh_dir)
        manager = BearerAuthManager(config)

        private_key = manager._generate_keypair()

        assert private_key is not None

        # Check files were created
        private_path = ssh_dir / "test.key"
        public_path = ssh_dir / "test.key.pub"
        assert private_path.exists()
        assert public_path.exists()

        # Check permissions
        assert oct(private_path.stat().st_mode)[-3:] == "600"

        # Verify SSH public key format
        with open(public_path, 'rb') as f:
            ssh_key = f.read()
            assert ssh_key.startswith(b'ssh-rsa ')

    def test_generate_keys_success(self, tmp_path):
        """Test successful keypair generation using generate_keys method."""
        # Use a temporary directory for SSH keys
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        config = BearerAuthConfig(audience="test", key_path=ssh_dir)
        manager = BearerAuthManager(config)

        manager.generate_keys()

        # Check internal state
        assert manager._private_key is not None
        assert manager._public_key is not None

        # Check files were created
        private_path = ssh_dir / "test.key"
        public_path = ssh_dir / "test.key.pub"
        assert private_path.exists()
        assert public_path.exists()

        # Check permissions
        assert oct(private_path.stat().st_mode)[-3:] == "600"

        # Verify SSH public key format
        with open(public_path, 'rb') as f:
            ssh_key = f.read()
            assert ssh_key.startswith(b'ssh-rsa ')

    def test_generate_keys_already_exists(self, tmp_path):
        """Test generate_keys raises error when keys already exist."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create existing key file
        key_file = ssh_dir / "test.key"
        key_file.write_text("existing key")

        config = BearerAuthConfig(audience="test", key_path=ssh_dir)
        manager = BearerAuthManager(config)

        with pytest.raises(RuntimeError, match="Private key already exists"):
            manager.generate_keys()


    def test_load_keys_no_private_key(self, tmp_path):
        """Test load_keys raises error when no private key found."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        config = BearerAuthConfig(audience="test", key_path=ssh_dir)
        manager = BearerAuthManager(config)

        with pytest.raises(RuntimeError, match="Authentication is not enabled"):
            manager.load_keys()

    def test_provider_property_calls_load_keys(self, tmp_path):
        """Test provider property automatically calls load_keys."""
        # Generate test key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        config = BearerAuthConfig(audience="test", key_path=ssh_dir)
        manager = BearerAuthManager(config)

        # Keys not loaded yet
        assert manager._private_key is None
        assert manager._public_key is None

        with patch.dict('os.environ', {'MAGG_PRIVATE_KEY': pem}):
            # Access provider property
            provider = manager.provider

            # Keys should now be loaded
            assert manager._private_key is not None
            assert manager._public_key is not None
            assert isinstance(provider, BearerAuthProvider)
