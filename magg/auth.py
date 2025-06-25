"""Authentication support for Magg."""
import logging
import time
from functools import cached_property
from typing import Optional

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastmcp.server.auth import BearerAuthProvider

from .settings import BearerAuthConfig

logger = logging.getLogger(__name__)


class BearerAuthManager:
    """Manages bearer token authentication keys and configuration."""

    def __init__(self, bearer_config: BearerAuthConfig):
        self.bearer_config = bearer_config
        self._private_key = None
        self._public_key = None

    @property
    def enabled(self) -> bool:
        """Check if authentication is enabled (private key exists)."""
        return self.bearer_config.private_key_exists

    def load_keys(self) -> None:
        """Load existing RSA keys.

        Raises:
            RuntimeError: If not enabled or keys cannot be loaded
        """
        if not self.enabled:
            raise RuntimeError("Authentication is not enabled")

        # Already loaded
        if self._private_key and self._public_key:
            return

        private_key = self._load_private_key()
        if private_key is None:
            raise RuntimeError(f"No private key found for audience '{self.bearer_config.audience}'")

        self._private_key = private_key
        self._public_key = self._derive_public_key(private_key)

    def generate_keys(self) -> None:
        """Generate new RSA keypair.

        Raises:
            RuntimeError: If keys already exist or generation fails
        """
        if self.bearer_config.private_key_exists:
            raise RuntimeError(f"Private key already exists at {self.bearer_config.private_key_path}. Remove it manually to regenerate.")

        private_key = self._generate_keypair()
        if private_key is None:
            raise RuntimeError("Failed to generate keypair")

        self._private_key = private_key
        self._public_key = self._derive_public_key(private_key)

    def _load_private_key(self) -> Optional[rsa.RSAPrivateKey]:
        """Load private key from env var or file."""
        key_data = self.bearer_config.private_key_data
        if not key_data:
            return None

        try:
            return serialization.load_pem_private_key(
                key_data.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
        except Exception as e:
            logger.error(f"Failed to load private key: {e}")
            return None

    def _generate_keypair(self) -> Optional[rsa.RSAPrivateKey]:
        """Generate new RSA keypair and save to files."""
        logger.debug(f"Generating new RSA keypair for audience '{self.bearer_config.audience}'")

        try:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            self.bearer_config.key_path.mkdir(mode=0o700, exist_ok=True)

            private_path = self.bearer_config.private_key_path

            with private_path.open('wb') as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            private_path.chmod(0o600)

            ssh_public_path = self.bearer_config.public_key_path
            public_key = private_key.public_key()
            with open(ssh_public_path, 'wb') as f:
                f.write(public_key.public_bytes(
                    encoding=serialization.Encoding.OpenSSH,
                    format=serialization.PublicFormat.OpenSSH
                ))

            logger.info(f"Generated new RSA keypair in {self.bearer_config.key_path}")
            return private_key

        except Exception as e:
            logger.error(f"Failed to generate keypair: {e}")
            return None

    @classmethod
    def _derive_public_key(cls, private_key: rsa.RSAPrivateKey) -> str:
        """Derive public key from private key."""
        public_key = private_key.public_key()

        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        return public_key_pem

    def get_public_key(self) -> Optional[str]:
        """Get the loaded public key in PEM format."""
        return self._public_key

    def get_private_key(self) -> Optional[rsa.RSAPrivateKey]:
        """Get the loaded private key."""
        return self._private_key

    @cached_property
    def provider(self) -> BearerAuthProvider:
        """Get the FastMCP BearerAuthProvider for server authentication.

        Returns:
            BearerAuthProvider instance

        Raises:
            RuntimeError: If authentication is not enabled or keys cannot be loaded
        """
        if not self.enabled:
            raise RuntimeError("Authentication is not enabled")

        self.load_keys()

        return BearerAuthProvider(
            public_key=self._public_key,
            issuer=self.bearer_config.issuer,
            audience=self.bearer_config.audience
        )

    def create_token(self, subject: str = "dev-user", hours: int = 24,
                    scopes: Optional[list[str]] = None) -> Optional[str]:
        """Create a JWT token for testing.

        Args:
            subject: Token subject (user identifier)
            hours: Token validity in hours
            scopes: Optional list of permission scopes

        Returns:
            JWT token string or None on error
        """
        if not self.enabled or not self._private_key:
            return None

        try:
            now = int(time.time())
            claims = {
                "iss": self.bearer_config.issuer,
                "aud": self.bearer_config.audience,
                "sub": subject,
                "iat": now,
                "exp": now + (hours * 3600),
            }

            # Add scopes if provided
            if scopes:
                claims["scope"] = " ".join(scopes)  # OAuth 2.0 uses space-separated scopes

            return jwt.encode(claims, self._private_key, algorithm="RS256")

        except Exception as e:
            logger.error(f"Failed to create token: {e}")
            return None
