"""Unit tests for server add functionality."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os

from magg import server as magg_server_module
from magg.core.config import MAGGConfig, MCPSource, MCPServer, ConfigManager


class TestAddServer:
    """Test magg_add_server functionality."""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock config manager with test data."""
        with patch('magg.server.config_manager') as mock_cm:
            # Create test config
            config = MAGGConfig()
            config.add_source(MCPSource(name="test-local", uri="file:///tmp/test-local"))
            config.add_source(MCPSource(name="remote-source", uri="https://github.com/example/repo"))
            
            mock_cm.load_config.return_value = config
            mock_cm.save_config = MagicMock()
            
            yield mock_cm
    
    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test directories
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            
            source_dir = Path(tmpdir) / "source"
            source_dir.mkdir()
            
            subdir = source_dir / "subdir"
            subdir.mkdir()
            
            yield {
                "tmpdir": tmpdir,
                "project_root": project_root,
                "source_dir": source_dir,
                "subdir": subdir
            }
    
    @pytest.mark.asyncio
    async def test_add_server_python_with_script(self, mock_config_manager, temp_dirs):
        """Test adding a Python server with script argument."""
        with patch('magg.server.mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = True
            
            # Instead of mocking get_project_root, mock validate_working_directory
            with patch('magg.utils.validate_working_directory') as mock_validate:
                # Return successful validation for valid directories
                def validate_side_effect(working_dir, source_uri):
                    if working_dir and Path(working_dir) == temp_dirs["project_root"]:
                        return None, "Working directory cannot be the project root"
                    elif working_dir and temp_dirs["source_dir"] in Path(working_dir).parents:
                        return Path(working_dir), None
                    elif working_dir == str(temp_dirs["subdir"]) or working_dir == str(temp_dirs["source_dir"]):
                        return Path(working_dir), None
                    elif not working_dir and source_uri and source_uri.startswith("file://"):
                        return Path(source_uri.replace("file://", "")), None
                    else:
                        return None, "Working directory must be within source directory"
                mock_validate.side_effect = validate_side_effect
                
                # Update source URI to use temp directory
                config = mock_config_manager.load_config()
                config.sources["test-local"].uri = f"file://{temp_dirs['source_dir']}"
                
                add_server_tool = getattr(magg_server_module, 'magg_add_server')
                if hasattr(add_server_tool, 'fn'):
                    result = await add_server_tool.fn(
                        name="test-python-server",
                        source_name="test-local",
                        command="python",
                        args=["server.py", "--port", "8080"],
                        working_dir=str(temp_dirs["subdir"])
                    )
                else:
                    result = await add_server_tool(
                        name="test-python-server",
                        source_name="test-local",
                        command="python",
                        args=["server.py", "--port", "8080"],
                        working_dir=str(temp_dirs["subdir"])
                    )
                
                assert "✅ Added and mounted server 'test-python-server'" in result
                assert "Command: python server.py --port 8080" in result
                
                # Verify server was created correctly
                saved_config = mock_config_manager.save_config.call_args[0][0]
                server = saved_config.servers["test-python-server"]
                assert server.command == "python"
                assert server.args == ["server.py", "--port", "8080"]
                assert server.working_dir == str(temp_dirs["subdir"])
    
    @pytest.mark.asyncio
    async def test_add_server_python_with_module(self, mock_config_manager, temp_dirs):
        """Test adding a Python server with -m module syntax."""
        with patch('magg.server.mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = True
            
            # Instead of mocking get_project_root, mock validate_working_directory
            with patch('magg.utils.validate_working_directory') as mock_validate:
                # Return successful validation for valid directories
                def validate_side_effect(working_dir, source_uri):
                    if working_dir and Path(working_dir) == temp_dirs["project_root"]:
                        return None, "Working directory cannot be the project root"
                    elif working_dir and temp_dirs["source_dir"] in Path(working_dir).parents:
                        return Path(working_dir), None
                    elif working_dir == str(temp_dirs["subdir"]) or working_dir == str(temp_dirs["source_dir"]):
                        return Path(working_dir), None
                    elif not working_dir and source_uri and source_uri.startswith("file://"):
                        return Path(source_uri.replace("file://", "")), None
                    else:
                        return None, "Working directory must be within source directory"
                mock_validate.side_effect = validate_side_effect
                
                # Update source URI to use temp directory
                config = mock_config_manager.load_config()
                config.sources["test-local"].uri = f"file://{temp_dirs['source_dir']}"
                
                add_server_tool = getattr(magg_server_module, 'magg_add_server')
                if hasattr(add_server_tool, 'fn'):
                    result = await add_server_tool.fn(
                        name="test-module-server",
                        source_name="test-local",
                        command="python",
                        args=["-m", "mypackage.server", "--debug"],
                        working_dir=str(temp_dirs["source_dir"])
                    )
                else:
                    result = await add_server_tool(
                        name="test-module-server",
                        source_name="test-local",
                        command="python",
                        args=["-m", "mypackage.server", "--debug"],
                        working_dir=str(temp_dirs["source_dir"])
                    )
                
                assert "✅ Added and mounted server 'test-module-server'" in result
                assert "Command: python -m mypackage.server --debug" in result
    
    @pytest.mark.asyncio
    async def test_add_server_working_dir_validation(self, mock_config_manager, temp_dirs):
        """Test working directory validation."""
        # Mock validate_working_directory to test validation logic
        with patch('magg.utils.validate_working_directory') as mock_validate:
            # Return error for project root
            mock_validate.return_value = (None, "Working directory cannot be the project root")
            
            # Test 1: Cannot use project root as working dir
            add_server_tool = getattr(magg_server_module, 'magg_add_server')
            if hasattr(add_server_tool, 'fn'):
                result = await add_server_tool.fn(
                    name="test-server",
                    source_name="test-local",
                    command="python",
                    args=["server.py"],
                    working_dir=str(temp_dirs["project_root"])
                )
            else:
                result = await add_server_tool(
                    name="test-server",
                    source_name="test-local",
                    command="python",
                    args=["server.py"],
                    working_dir=str(temp_dirs["project_root"])
                )
            
            assert "❌ Working directory cannot be the project root" in result
    
    @pytest.mark.asyncio
    async def test_add_server_working_dir_must_be_in_source(self, mock_config_manager, temp_dirs):
        """Test that working dir must be within source dir for local sources."""
        # Mock validate_working_directory to test validation logic
        with patch('magg.utils.validate_working_directory') as mock_validate:
            # Return error for project root
            mock_validate.return_value = (None, "Working directory cannot be the project root")
            
            # Update source URI to use temp directory
            config = mock_config_manager.load_config()
            config.sources["test-local"].uri = f"file://{temp_dirs['source_dir']}"
            
            # Try to use a directory outside the source
            other_dir = Path(temp_dirs["tmpdir"]) / "other"
            other_dir.mkdir()
            
            add_server_tool = getattr(magg_server_module, 'magg_add_server')
            if hasattr(add_server_tool, 'fn'):
                result = await add_server_tool.fn(
                    name="test-server",
                    source_name="test-local",
                    command="python",
                    args=["server.py"],
                    working_dir=str(other_dir)
                )
            else:
                result = await add_server_tool(
                    name="test-server",
                    source_name="test-local",
                    command="python",
                    args=["server.py"],
                    working_dir=str(other_dir)
                )
            
            assert "❌ Working directory must be within source directory" in result
    
    @pytest.mark.asyncio
    async def test_add_server_auto_working_dir(self, mock_config_manager, temp_dirs):
        """Test automatic working directory from source."""
        with patch('magg.server.mount_server', new_callable=AsyncMock) as mock_mount:
            mock_mount.return_value = True
            
            # Instead of mocking get_project_root, mock validate_working_directory
            with patch('magg.utils.validate_working_directory') as mock_validate:
                # Return successful validation for valid directories
                def validate_side_effect(working_dir, source_uri):
                    if working_dir and Path(working_dir) == temp_dirs["project_root"]:
                        return None, "Working directory cannot be the project root"
                    elif working_dir and temp_dirs["source_dir"] in Path(working_dir).parents:
                        return Path(working_dir), None
                    elif working_dir == str(temp_dirs["subdir"]) or working_dir == str(temp_dirs["source_dir"]):
                        return Path(working_dir), None
                    elif not working_dir and source_uri and source_uri.startswith("file://"):
                        return Path(source_uri.replace("file://", "")), None
                    else:
                        return None, "Working directory must be within source directory"
                mock_validate.side_effect = validate_side_effect
                
                # Update source URI to use temp directory
                config = mock_config_manager.load_config()
                config.sources["test-local"].uri = f"file://{temp_dirs['source_dir']}"
                
                # Don't provide working_dir - should use source dir
                add_server_tool = getattr(magg_server_module, 'magg_add_server')
                if hasattr(add_server_tool, 'fn'):
                    result = await add_server_tool.fn(
                        name="test-auto-dir",
                        source_name="test-local",
                        command="python",
                        args=["server.py"]
                    )
                else:
                    result = await add_server_tool(
                        name="test-auto-dir",
                        source_name="test-local",
                        command="python",
                        args=["server.py"]
                    )
                
                assert "✅ Added and mounted server 'test-auto-dir'" in result
                
                # Verify working_dir was set to source dir
                saved_config = mock_config_manager.save_config.call_args[0][0]
                server = saved_config.servers["test-auto-dir"]
                assert server.working_dir == str(temp_dirs["source_dir"])
    
    @pytest.mark.asyncio
    async def test_add_server_remote_source_requires_working_dir(self, mock_config_manager):
        """Test that remote sources require explicit working_dir."""
        with patch('magg.server.get_project_root') as mock_project_root:
            mock_project_root.return_value = Path("/tmp/project")
            
            add_server_tool = getattr(magg_server_module, 'magg_add_server')
            if hasattr(add_server_tool, 'fn'):
                result = await add_server_tool.fn(
                    name="remote-server",
                    source_name="remote-source",
                    command="python",
                    args=["server.py"]
                    # No working_dir provided
                )
            else:
                result = await add_server_tool(
                    name="remote-server",
                    source_name="remote-source",
                    command="python",
                    args=["server.py"]
                    # No working_dir provided
                )
            
            assert "❌ Working directory required for remote sources" in result
    
    @pytest.mark.asyncio
    async def test_add_server_source_not_found(self, mock_config_manager):
        """Test error when source doesn't exist."""
        add_server_tool = getattr(magg_server_module, 'magg_add_server')
        if hasattr(add_server_tool, 'fn'):
            result = await add_server_tool.handler(
                name="test-server",
                source_name="nonexistent-source",
                command="python",
                args=["server.py"]
            )
        else:
            result = await add_server_tool(
                name="test-server",
                source_name="nonexistent-source",
                command="python",
                args=["server.py"]
            )
        
        assert "❌ Source 'nonexistent-source' not found" in result
    
    @pytest.mark.asyncio
    async def test_add_server_duplicate_name(self, mock_config_manager):
        """Test error when server name already exists."""
        # Add a server first
        config = mock_config_manager.load_config()
        config.add_server(MCPServer(
            name="existing-server",
            source_name="test-local",
            command="python",
            args=["old.py"]
        ))
        
        add_server_tool = getattr(magg_server_module, 'magg_add_server')
        if hasattr(add_server_tool, 'fn'):
            result = await add_server_tool.handler(
                name="existing-server",
                source_name="test-local",
                command="python",
                args=["new.py"]
            )
        else:
            result = await add_server_tool(
                name="existing-server",
                source_name="test-local",
                command="python",
                args=["new.py"]
            )
        
        assert "❌ Server 'existing-server' already exists" in result


class TestAddSource:
    """Test magg_add_source functionality."""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock config manager."""
        with patch('magg.server.config_manager') as mock_cm:
            mock_cm.load_config.return_value = MAGGConfig()
            mock_cm.save_config = MagicMock()
            mock_cm.config_path = Path("/tmp/test/.magg/config.json")
            yield mock_cm
    
    @pytest.mark.asyncio
    async def test_add_source_name_only(self, mock_config_manager):
        """Test adding a source with just a name."""
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            # Mock metadata collection
            with patch('magg.discovery.metadata.SourceMetadataCollector') as mock_collector:
                mock_collector.return_value.collect_metadata = AsyncMock(return_value=[])
                
                add_source_tool = getattr(magg_server_module, 'magg_add_source')
                if hasattr(add_source_tool, 'fn'):
                    result = await add_source_tool.fn(name="my-local-source")
                else:
                    result = await add_source_tool(name="my-local-source")
                
                assert "✅ Added source 'my-local-source'" in result
                # The result message format changed - now it just says the source was added
                
                # Verify directory creation was attempted
                mock_mkdir.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_source_with_uri(self, mock_config_manager):
        """Test adding a source with explicit URI."""
        with patch('magg.discovery.metadata.SourceMetadataCollector') as mock_collector:
            mock_collector.return_value.collect_metadata = AsyncMock(return_value=[])
            
            add_source_tool = getattr(magg_server_module, 'magg_add_source')
            if hasattr(add_source_tool, 'fn'):
                result = await add_source_tool.fn(
                    name="github-source",
                    uri="https://github.com/example/repo"
                )
            else:
                result = await add_source_tool(
                    name="github-source",
                    uri="https://github.com/example/repo"
                )
            
            assert "✅ Added source 'github-source'" in result
            # The result message format changed - now it just says the source was added
    
    @pytest.mark.asyncio
    async def test_add_source_duplicate_name(self, mock_config_manager):
        """Test error when source name already exists."""
        config = mock_config_manager.load_config()
        config.add_source(MCPSource(name="existing", uri="file:///tmp/existing"))
        
        add_source_tool = getattr(magg_server_module, 'magg_add_source')
        if hasattr(add_source_tool, 'fn'):
            result = await add_source_tool.fn(name="existing")
        else:
            result = await add_source_tool(name="existing")
        
        assert "❌ Source 'existing' already exists" in result