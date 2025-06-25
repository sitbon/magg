"""Unit tests for server add functionality."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import tempfile

from magg.server import MaggServer
from magg.settings import MaggConfig


class TestAddServer:
    """Test magg_add_server functionality."""

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock config manager with test data."""
        config = MaggConfig()
        return config

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test directories
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            working_dir = Path(tmpdir) / "work"
            working_dir.mkdir()

            subdir = working_dir / "subdir"
            subdir.mkdir()

            yield {
                "tmpdir": tmpdir,
                "project_root": project_root,
                "working_dir": working_dir,
                "subdir": subdir
            }

    @pytest.fixture
    def magg_server(self, temp_dirs):
        """Create a Magg server instance for testing."""
        with tempfile.TemporaryDirectory() as config_dir:
            config_path = Path(config_dir) / "config.json"
            server = MaggServer(str(config_path))
            yield server

    @pytest.mark.asyncio
    async def test_add_server_python_with_script(self, magg_server, temp_dirs):
        """Test adding a Python server with script argument."""
        with patch.object(magg_server.server_manager, 'mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = True

            # Mock validate_working_directory
            with patch('magg.server.server.validate_working_directory') as mock_validate:
                mock_validate.return_value = (Path(temp_dirs["subdir"]), None)

                result = await magg_server.add_server(
                    name="testpythonserver",
                    source="https://github.com/example/test",
                    command="python server.py --port 8080",
                    working_dir=str(temp_dirs["subdir"])
                )

                assert result.is_success
                assert result.output["action"] == "server_added"
                assert result.output["server"]["name"] == "testpythonserver"
                assert result.output["server"]["command"] == "python server.py --port 8080"
                assert result.output["server"]["mounted"] is True

    @pytest.mark.asyncio
    async def test_add_server_python_with_module(self, magg_server, temp_dirs):
        """Test adding a Python server with -m module syntax."""
        with patch.object(magg_server.server_manager, 'mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = True

            with patch('magg.server.server.validate_working_directory') as mock_validate:
                mock_validate.return_value = (Path(temp_dirs["working_dir"]), None)

                result = await magg_server.add_server(
                    name="testmoduleserver",
                    source="https://github.com/example/test",
                    command="python -m mypackage.server --debug",
                    working_dir=str(temp_dirs["working_dir"])
                )

                assert result.is_success
                assert result.output["server"]["command"] == "python -m mypackage.server --debug"

    @pytest.mark.asyncio
    async def test_add_server_working_dir_validation_error(self, magg_server, temp_dirs):
        """Test working directory validation error."""
        with patch('magg.server.server.validate_working_directory') as mock_validate:
            mock_validate.return_value = (None, "Working directory cannot be the project root")

            result = await magg_server.add_server(
                name="testserver",
                source="https://github.com/example/test",
                command="python server.py",
                working_dir=str(temp_dirs["project_root"])
            )

            assert result.is_error
            assert "Working directory cannot be the project root" in result.errors[0]

    @pytest.mark.asyncio
    async def test_add_server_duplicate_name(self, magg_server):
        """Test error when server name already exists."""
        # Add a server first
        with patch.object(magg_server.server_manager, 'mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = True

            # First server
            result1 = await magg_server.add_server(
                name="existingserver",
                source="https://github.com/example/test1",
                command="python old.py"
            )
            assert result1.is_success

            # Try to add duplicate
            result2 = await magg_server.add_server(
                name="existingserver",
                source="https://github.com/example/test2",
                command="python new.py"
            )

            assert result2.is_error
            assert "Server 'existingserver' already exists" in result2.errors[0]

    @pytest.mark.asyncio
    async def test_add_server_invalid_name_accepted(self, magg_server):
        """Test that invalid names are now accepted with auto-generated prefix."""
        result = await magg_server.add_server(
            name="123-invalid",
            source="https://github.com/example/test",
            command="python server.py"
        )

        assert result.is_success
        assert result.output["server"]["name"] == "123-invalid"
        assert result.output["server"]["prefix"] == "srv123invalid"  # Auto-generated prefix

    @pytest.mark.asyncio
    async def test_add_server_invalid_prefix(self, magg_server):
        """Test error when prefix is invalid identifier."""
        result = await magg_server.add_server(
            name="validname",
            source="https://github.com/example/test",
            prefix="invalid-prefix",
            command="python server.py"
        )

        assert result.is_error
        assert "must be a valid Python identifier" in result.errors[0]

    @pytest.mark.asyncio
    async def test_add_server_with_env_vars(self, magg_server):
        """Test adding a server with environment variables."""
        with patch.object(magg_server.server_manager, 'mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = True

            result = await magg_server.add_server(
                name="envtestserver",
                source="https://github.com/example/test",
                command="node server.js",
                env_vars={"NODE_ENV": "production", "PORT": "3000"}
            )

            assert result.is_success
            assert result.output["server"]["name"] == "envtestserver"

    @pytest.mark.asyncio
    async def test_add_server_http_no_command(self, magg_server):
        """Test adding an HTTP server without command."""
        with patch.object(magg_server.server_manager, 'mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = True

            result = await magg_server.add_server(
                name="httpserver",
                source="https://github.com/example/test",
                uri="http://localhost:8080"
            )

            assert result.is_success
            assert result.output["server"]["uri"] == "http://localhost:8080"
            assert result.output["server"]["command"] is None

    @pytest.mark.asyncio
    async def test_add_server_mount_failure(self, magg_server):
        """Test handling of mount failure."""
        with patch.object(magg_server.server_manager, 'mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = False

            result = await magg_server.add_server(
                name="failserver",
                source="https://github.com/example/test",
                command="python server.py"
            )

            assert result.is_error
            assert "Failed to mount server" in result.errors[0]

    @pytest.mark.asyncio
    async def test_add_server_with_notes(self, magg_server):
        """Test adding a server with notes."""
        with patch.object(magg_server.server_manager, 'mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = True

            result = await magg_server.add_server(
                name="documentedserver",
                source="https://github.com/example/test",
                command="npm start",
                notes="This server requires Node.js 18+"
            )

            assert result.is_success
            assert result.output["server"]["notes"] == "This server requires Node.js 18+"

    @pytest.mark.asyncio
    async def test_add_server_disabled(self, magg_server):
        """Test adding a disabled server."""
        with patch.object(magg_server.server_manager, 'mount_server', new_callable=AsyncMock) as mock_mount:
            # Should not be called for disabled server

            result = await magg_server.add_server(
                name="disabledserver",
                source="https://github.com/example/test",
                command="python server.py",
                enable=False
            )

            assert result.is_success
            assert result.output["server"]["enabled"] is False
            assert result.output["server"]["mounted"] is None, "Server not mounted"
            mock_mount.assert_not_called()  # Should not attempt to mount
