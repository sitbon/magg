"""Test error handling for invalid servers and edge cases."""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


class TestErrorHandling:
    """Test error handling for various failure scenarios."""
    
    @pytest.mark.asyncio
    async def test_invalid_server_connection(self):
        """Test handling of invalid server connections."""
        from magg.core.config import ConfigManager, MCPServer
        
        # Create a server config with invalid command
        invalid_server = MCPServer(
            name="invalid-server",
            source_url="https://example.com/invalid",
            prefix="invalid",
            command=["nonexistent-command", "--invalid-args"]
        )
        
        # Test that the invalid server is handled gracefully
        assert invalid_server.command == ["nonexistent-command", "--invalid-args"]
    
    @pytest.mark.asyncio
    async def test_malformed_config_handling(self):
        """Test handling of malformed configuration files."""
        from magg.core.config import ConfigManager, MAGGConfig
        import tempfile
        from pathlib import Path
        
        # Create malformed config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"sources": {"invalid": "malformed"}')  # Invalid JSON
            config_path = Path(f.name)
        
        try:
            config_manager = ConfigManager(str(config_path))
            
            # Should handle malformed config gracefully by returning empty config
            config = config_manager.load_config()
            assert isinstance(config, MAGGConfig)
            assert len(config.sources) == 0  # Should be empty due to error
            assert len(config.servers) == 0
        finally:
            if config_path.exists():
                config_path.unlink()
    
    @pytest.mark.asyncio
    async def test_missing_command_handling(self):
        """Test handling of servers with missing commands."""
        from magg.core.config import MCPServer
        
        # Create server with no command or URI
        incomplete_server = MCPServer(
            name="incomplete-server",
            source_url="https://example.com/incomplete",
            prefix="incomplete"
            # No command or uri specified
        )
        
        # Should handle missing connection details
        assert incomplete_server.command is None
        assert incomplete_server.uri is None
    
    @pytest.mark.asyncio
    async def test_duplicate_server_names(self):
        """Test handling of duplicate server names."""
        from magg.core.config import MAGGConfig, MCPServer
        
        config = MAGGConfig()
        
        # Add first server
        server1 = MCPServer(name="duplicate", source_url="https://example.com/1", prefix="dup1")
        config.add_server(server1)
        
        # Add second server with same name (should replace)
        server2 = MCPServer(name="duplicate", source_url="https://example.com/2", prefix="dup2")
        config.add_server(server2)
        
        # Should only have one server with the name
        assert len(config.servers) == 1
        assert config.servers["duplicate"].source_url == "https://example.com/2"
        assert config.servers["duplicate"].prefix == "dup2"
    
    @pytest.mark.asyncio
    async def test_circular_dependency_handling(self):
        """Test handling of potential circular dependencies."""
        from magg.core.config import MAGGConfig, MCPSource, MCPServer
        
        config = MAGGConfig()
        
        # Add source
        source = MCPSource(url="https://example.com/circular", name="circular")
        config.add_source(source)
        
        # Add server that references the source
        server = MCPServer(
            name="circular-server",
            source_url="https://example.com/circular",
            prefix="circular"
        )
        config.add_server(server)
        
        # Should handle removal without issues
        removed = config.remove_source("https://example.com/circular")
        assert removed is True
        assert len(config.sources) == 0
        assert len(config.servers) == 0  # Server should be removed too
    
    @pytest.mark.asyncio
    async def test_invalid_url_format_handling(self):
        """Test handling of invalid URL formats."""
        from magg.core.config import MCPSource
        
        # Test various invalid URL formats
        invalid_urls = [
            "not-a-url",
            "ftp://invalid-scheme.com",
            "   ",  # whitespace only
            "",     # empty string
        ]
        
        for invalid_url in invalid_urls:
            # Should create source but with potentially modified name
            source = MCPSource(url=invalid_url)
            assert source.url == invalid_url
            # Name generation should handle invalid URLs gracefully
            assert isinstance(source.name, str)
            assert len(source.name) > 0
    
    @pytest.mark.asyncio 
    async def test_environment_variable_handling(self):
        """Test handling of environment variables in server config."""
        from magg.core.config import MCPServer
        
        # Create server with environment variables
        server = MCPServer(
            name="env-server",
            source_url="https://example.com/env",
            prefix="env",
            env={"INVALID_VAR": None, "EMPTY_VAR": "", "VALID_VAR": "value"}
        )
        
        # Should handle various env var values
        assert server.env["INVALID_VAR"] is None
        assert server.env["EMPTY_VAR"] == ""
        assert server.env["VALID_VAR"] == "value"


class TestConfigValidation:
    """Test configuration validation and error cases."""
    
    def test_empty_config_creation(self):
        """Test creating empty configuration doesn't error."""
        from magg.core.config import MAGGConfig
        
        config = MAGGConfig()
        assert len(config.sources) == 0
        assert len(config.servers) == 0
    
    def test_source_without_url(self):
        """Test source creation requires URL."""
        from magg.core.config import MCPSource
        
        # URL is required parameter
        with pytest.raises(TypeError):
            MCPSource()  # Missing required url parameter
    
    def test_server_without_required_fields(self):
        """Test server creation requires certain fields."""
        from magg.core.config import MCPServer
        
        # Name and source_url are required
        with pytest.raises(TypeError):
            MCPServer()  # Missing required parameters
            
        with pytest.raises(TypeError):
            MCPServer(name="test")  # Missing source_url