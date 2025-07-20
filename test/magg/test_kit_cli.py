"""Tests for kit CLI commands."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock, call
import sys
import io
import contextlib

from magg.cli import cmd_kit
from magg.kit import KitConfig
from magg.settings import ServerConfig, MaggConfig


class TestKitCLI:
    """Test kit CLI commands."""

    @pytest.fixture
    def mock_args(self):
        """Create mock args object."""
        args = MagicMock()
        args.config = None
        return args

    @pytest.fixture
    def mock_kit_manager(self):
        """Create mock kit manager with test kits."""
        manager = MagicMock()

        # Mock discover_kits
        manager.discover_kits.return_value = {
            'test-kit': Path('/mock/kit.d/test-kit.json'),
            'empty-kit': Path('/mock/kit.d/empty-kit.json')
        }

        # Mock load_kit
        def mock_load_kit(path):
            if 'test-kit' in str(path):
                kit = KitConfig(
                    name='test-kit',
                    description='Test kit for unit tests',
                    author='Test Author',
                    version='1.0.0',
                    keywords=['test', 'example'],
                    links={'homepage': 'https://example.com'},
                    servers={
                        'test-server': ServerConfig(
                            name='test-server',
                            source='https://example.com/test',
                            command='echo',
                            args=['test'],
                            notes='Test server'
                        )
                    }
                )
                return kit
            elif 'empty-kit' in str(path):
                return KitConfig(name='empty-kit', description='Empty kit')
            return None

        manager.load_kit.side_effect = mock_load_kit
        manager.kitd_paths = [Path('/mock/kit.d')]

        return manager

    @pytest.mark.asyncio
    async def test_kit_list(self, mock_args, mock_kit_manager, capsys):
        """Test kit list command."""
        mock_args.kit_action = 'list'

        # Patch KitManager at the cli module level where it's used
        with patch('magg.cli.KitManager', return_value=mock_kit_manager):
            with patch('magg.cli.ConfigManager'):
                await cmd_kit(mock_args)

        captured = capsys.readouterr()
        # All output goes to stderr for consistency
        assert 'Available kits (2)' in captured.err
        assert 'test-kit: Test kit for unit tests' in captured.err
        assert 'empty-kit: Empty kit' in captured.err

    @pytest.mark.asyncio
    async def test_kit_list_empty(self, mock_args, capsys):
        """Test kit list when no kits found."""
        mock_args.kit_action = 'list'

        manager = MagicMock()
        manager.discover_kits.return_value = {}
        manager.kitd_paths = [Path('/mock/kit.d')]

        with patch('magg.cli.KitManager', return_value=manager):
            with patch('magg.cli.ConfigManager'):
                await cmd_kit(mock_args)

        captured = capsys.readouterr()
        assert 'No kits found' in captured.err
        assert 'Search paths:' in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_success(self, mock_args, mock_kit_manager, capsys):
        """Test successful kit load."""
        mock_args.kit_action = 'load'
        mock_args.name = 'test-kit'
        mock_args.enable = True

        # Mock config
        config = MaggConfig()
        config.kits = {}
        config.servers = {}

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = True

        with patch('magg.cli.KitManager', return_value=mock_kit_manager):
            with patch('magg.cli.ConfigManager', return_value=mock_config_instance):
                await cmd_kit(mock_args)

        # Check that server was added
        assert 'test-server' in config.servers
        assert config.servers['test-server'].enabled is True
        assert 'test-kit' in config.kits

        # Check output
        captured = capsys.readouterr()
        assert 'Added 1 servers from kit' in captured.err
        assert 'test-server (enabled)' in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_no_enable(self, mock_args, mock_kit_manager, capsys):
        """Test kit load with --no-enable flag."""
        mock_args.kit_action = 'load'
        mock_args.name = 'test-kit'
        mock_args.enable = False

        # Mock config
        config = MaggConfig()
        config.kits = {}
        config.servers = {}

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = True

        with patch('magg.cli.KitManager', return_value=mock_kit_manager):
            with patch('magg.cli.ConfigManager', return_value=mock_config_instance):
                await cmd_kit(mock_args)

        # Check that server was added but disabled
        assert 'test-server' in config.servers
        assert config.servers['test-server'].enabled is False

        # Check output
        captured = capsys.readouterr()
        assert 'test-server (disabled)' in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_not_found(self, mock_args, mock_kit_manager, capsys):
        """Test kit load with non-existent kit."""
        mock_args.kit_action = 'load'
        mock_args.name = 'nonexistent-kit'

        with patch('magg.cli.KitManager', return_value=mock_kit_manager):
            with patch('magg.cli.ConfigManager'):
                result = await cmd_kit(mock_args)
                assert result == 1

        captured = capsys.readouterr()
        assert "Kit 'nonexistent-kit' not found" in captured.err
        assert 'Available kits: test-kit, empty-kit' in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_skip_existing(self, mock_args, mock_kit_manager, capsys):
        """Test kit load skips existing servers."""
        mock_args.kit_action = 'load'
        mock_args.name = 'test-kit'
        mock_args.enable = True

        # Mock config with existing server
        config = MaggConfig()
        config.kits = {}
        config.servers = {
            'test-server': ServerConfig(
                name='test-server',
                source='https://different.com',
                command='different'
            )
        }

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = True

        with patch('magg.cli.KitManager', return_value=mock_kit_manager):
            with patch('magg.cli.ConfigManager', return_value=mock_config_instance):
                await cmd_kit(mock_args)

        # Check that existing server was not overwritten
        assert config.servers['test-server'].source == 'https://different.com'

        # Check output
        captured = capsys.readouterr()
        assert 'Skipped 1 servers already in configuration' in captured.err
        assert 'test-server' in captured.err

    @pytest.mark.asyncio
    async def test_kit_info(self, mock_args, mock_kit_manager, capsys):
        """Test kit info command."""
        mock_args.kit_action = 'info'
        mock_args.name = 'test-kit'

        # Since KitManager is imported inside the function, patch at the module level
        with patch('magg.cli.KitManager', return_value=mock_kit_manager):
            with patch('magg.cli.ConfigManager'):
                await cmd_kit(mock_args)

        captured = capsys.readouterr()
        assert 'Kit: test-kit' in captured.err
        assert 'Description: Test kit for unit tests' in captured.err
        assert 'Author: Test Author' in captured.err
        assert 'Version: 1.0.0' in captured.err
        assert 'Keywords: test, example' in captured.err
        assert 'homepage: https://example.com' in captured.err
        assert 'Servers (1):' in captured.err
        assert 'test-server' in captured.err
        assert 'Test server' in captured.err

    @pytest.mark.asyncio
    async def test_kit_info_not_found(self, mock_args, mock_kit_manager, capsys):
        """Test kit info with non-existent kit."""
        mock_args.kit_action = 'info'
        mock_args.name = 'nonexistent-kit'

        with patch('magg.cli.KitManager', return_value=mock_kit_manager):
            with patch('magg.cli.ConfigManager'):
                result = await cmd_kit(mock_args)
                assert result == 1

        captured = capsys.readouterr()
        assert "Kit 'nonexistent-kit' not found" in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_empty_kit(self, mock_args, mock_kit_manager, capsys):
        """Test loading a kit with no servers."""
        mock_args.kit_action = 'load'
        mock_args.name = 'empty-kit'
        mock_args.enable = True

        # Mock config
        config = MaggConfig()
        config.kits = {}
        config.servers = {}

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = True

        with patch('magg.cli.KitManager', return_value=mock_kit_manager):
            with patch('magg.cli.ConfigManager', return_value=mock_config_instance):
                await cmd_kit(mock_args)

        # Check output
        captured = capsys.readouterr()
        assert "Kit 'empty-kit' contains no servers" in captured.err

    @pytest.mark.asyncio
    async def test_kit_load_save_failure(self, mock_args, mock_kit_manager, capsys):
        """Test kit load when config save fails."""
        mock_args.kit_action = 'load'
        mock_args.name = 'test-kit'
        mock_args.enable = True

        # Mock config
        config = MaggConfig()
        config.kits = {}
        config.servers = {}

        mock_config_instance = MagicMock()
        mock_config_instance.load_config.return_value = config
        mock_config_instance.save_config.return_value = False  # Simulate save failure

        with patch('magg.cli.KitManager', return_value=mock_kit_manager):
            with patch('magg.cli.ConfigManager', return_value=mock_config_instance):
                result = await cmd_kit(mock_args)
                assert result == 1

        captured = capsys.readouterr()
        assert 'Failed to save configuration' in captured.err
