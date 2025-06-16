"""Integration tests for MAGG server functionality."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from magg import server as magg_server_module
from magg.core.config import MAGGConfig, ConfigManager


class TestIntegration:
    """Test full integration of source and server creation."""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock config manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".magg" / "config.json"
            config_path.parent.mkdir(parents=True)
            
            with patch('magg.server.config_manager') as mock_cm:
                mock_cm.config_path = config_path
                mock_cm.load_config = MagicMock(return_value=MAGGConfig())
                mock_cm.save_config = MagicMock(return_value=True)
                
                yield mock_cm
    
    @pytest.mark.asyncio
    async def test_add_local_source_and_python_server(self, mock_config_manager):
        """Test adding a local source and Python server with server.py."""
        # Mock metadata collection
        with patch('magg.discovery.metadata.SourceMetadataCollector') as mock_collector:
            mock_collector.return_value.collect_metadata = AsyncMock(return_value=[])
            
            # Add local source - access the handler function
            add_source_tool = getattr(magg_server_module, 'magg_add_source')
            if hasattr(add_source_tool, 'fn'):
                # It's a FunctionTool, use the handler
                result = await add_source_tool.fn(name="test-local")
            else:
                # Direct function call
                result = await add_source_tool(name="test-local")
            assert "✅ Added source 'test-local'" in result
            # Result format changed - no longer includes the URI in output
            
            # Get the config that was saved
            saved_config = mock_config_manager.save_config.call_args[0][0]
            assert "test-local" in saved_config.sources
            source = saved_config.sources["test-local"]
            assert source.uri.startswith("file://")
            
            # Update mock to return this config
            mock_config_manager.load_config.return_value = saved_config
            
            # Create the source directory and server.py
            source_dir = source.uri.replace("file://", "")
            Path(source_dir).mkdir(parents=True, exist_ok=True)
            server_file = Path(source_dir) / "server.py"
            server_file.write_text("print('test server')")
            
            # Mock mount_server
            with patch('magg.server.mount_server', new_callable=AsyncMock) as mock_mount:
                mock_mount.return_value = True
                
                # Add server - access the handler function
                add_server_tool = getattr(magg_server_module, 'magg_add_server')
                if hasattr(add_server_tool, 'fn'):
                    # It's a FunctionTool, use the handler
                    result = await add_server_tool.fn(
                        name="test-python-server",
                        source_name="test-local",
                        command="python",
                        args=["server.py"],
                        working_dir=source_dir
                    )
                else:
                    # Direct function call
                    result = await add_server_tool(
                        name="test-python-server",
                        source_name="test-local",
                        command="python",
                        args=["server.py"],
                        working_dir=source_dir
                    )
                
                assert "✅ Added and mounted server 'test-python-server'" in result
                assert "Command: python server.py" in result
                
                # Verify mount_server was called
                mock_mount.assert_called_once()
                server_arg = mock_mount.call_args[0][0]
                assert server_arg.name == "test-python-server"
                assert server_arg.command == "python"
                assert server_arg.args == ["server.py"]
                assert server_arg.working_dir == source_dir
    
    @pytest.mark.asyncio 
    async def test_add_server_with_python_module(self, mock_config_manager):
        """Test adding a Python server with -m module syntax."""
        # Set up a source first
        config = MAGGConfig()
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "mypackage"
            source_dir.mkdir()
            
            from magg.core.config import MCPSource
            source = MCPSource(name="mypackage", uri=f"file://{source_dir}")
            config.add_source(source)
            mock_config_manager.load_config.return_value = config
            
            # Mock mount_server
            with patch('magg.server.mount_server', new_callable=AsyncMock) as mock_mount:
                mock_mount.return_value = True
                
                # Add server with -m - access the handler function
                add_server_tool = getattr(magg_server_module, 'magg_add_server')
                if hasattr(add_server_tool, 'fn'):
                    # It's a FunctionTool, use the handler
                    result = await add_server_tool.fn(
                        name="module-server",
                        source_name="mypackage",
                        command="python",
                        args=["-m", "mypackage.server", "--debug"],
                        working_dir=str(source_dir)
                    )
                else:
                    # Direct function call
                    result = await add_server_tool(
                        name="module-server",
                        source_name="mypackage",
                        command="python",
                        args=["-m", "mypackage.server", "--debug"],
                        working_dir=str(source_dir)
                    )
                
                assert "✅ Added and mounted server 'module-server'" in result
                assert "Command: python -m mypackage.server --debug" in result
                
                # Verify the server was configured correctly
                server_arg = mock_mount.call_args[0][0]
                assert server_arg.command == "python"
                assert server_arg.args == ["-m", "mypackage.server", "--debug"]
    
    @pytest.mark.asyncio
    async def test_transport_selection(self, mock_config_manager):
        """Test that correct transports are selected for different commands."""
        from magg.utils.transport import get_transport_for_command
        from magg.utils.custom_transports import NoValidatePythonStdioTransport
        from fastmcp.client.transports import NpxStdioTransport, StdioTransport
        
        # Test Python transport
        with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as f:
            f.write(b"print('test')")
            f.flush()
            
            transport = get_transport_for_command(
                command="python",
                args=[f.name]
            )
            assert isinstance(transport, NoValidatePythonStdioTransport)
            os.unlink(f.name)
        
        # Test NPX transport
        transport = get_transport_for_command(
            command="npx",
            args=["some-package"]
        )
        assert isinstance(transport, NpxStdioTransport)
        
        # Test generic command falls back to StdioTransport
        transport = get_transport_for_command(
            command="/usr/bin/custom",
            args=["--help"]
        )
        assert isinstance(transport, StdioTransport)