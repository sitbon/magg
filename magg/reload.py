"""Configuration reload functionality for Magg server."""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Coroutine, TypeAlias

from .settings import MaggConfig, ServerConfig

logger = logging.getLogger(__name__)

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

ReloadCallback: TypeAlias = Callable[['ConfigChange'], Coroutine[None, None, None]]


@dataclass
class ServerChange:
    """Represents a change to a server configuration."""
    name: str
    action: str  # 'add', 'remove', 'update', 'enable', 'disable'
    old_config: ServerConfig | None = None
    new_config: ServerConfig | None = None


@dataclass
class ConfigChange:
    """Represents changes between two configurations."""
    old_config: MaggConfig
    new_config: MaggConfig
    server_changes: list[ServerChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if there are any server changes."""
        return bool(self.server_changes)

    def summarize(self) -> str:
        """Get a summary of changes."""
        if not self.has_changes:
            return "No changes detected"

        summary = []
        for change in self.server_changes:
            if change.action == 'add':
                summary.append(f"+ {change.name}")
            elif change.action == 'remove':
                summary.append(f"- {change.name}")
            elif change.action == 'update':
                summary.append(f"~ {change.name}")
            elif change.action == 'enable':
                summary.append(f"✓ {change.name}")
            elif change.action == 'disable':
                summary.append(f"✗ {change.name}")

        return f"Config changes: {', '.join(summary)}"


class WatchdogHandler(FileSystemEventHandler):
    """Watchdog event handler for config file changes."""

    def __init__(self, config_path: Path, reload_event: asyncio.Event):
        self.config_path = config_path
        self.reload_event = reload_event
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            # Not in an async context, get the event loop
            self._loop = asyncio.get_event_loop()

    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory and Path(event.src_path) == self.config_path:
            # Schedule the reload event in the asyncio loop
            self._loop.call_soon_threadsafe(self.reload_event.set)


class ConfigReloader:
    """Manages configuration reloading with file watching and diff detection."""

    def __init__(self, config_path: Path, reload_callback: ReloadCallback):
        """Initialize the config reloader.

        Args:
            config_path: Path to the configuration file
            reload_callback: Async callback to handle config changes
        """
        self.config_path = config_path
        self.reload_callback = reload_callback
        self._last_mtime: float | None = None
        self._last_config: MaggConfig | None = None
        self._watch_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._reload_lock = asyncio.Lock()
        self._reload_event = asyncio.Event()
        self._ignore_next_change = False
        self._observer: Observer | None = None
        self._watchdog_handler: WatchdogHandler | None = None

    async def start_watching(self, poll_interval: float = 1.0) -> None:
        """Start watching the config file for changes.

        Args:
            poll_interval: How often to check for changes (seconds) - only used for polling mode
        """
        if self._watch_task and not self._watch_task.done():
            logger.warning("Config watcher already running")
            return

        self._shutdown_event.clear()
        self._reload_event.clear()

        # Try to start watchdog observer
        try:
            self._observer = Observer()
            self._watchdog_handler = WatchdogHandler(self.config_path, self._reload_event)
            self._observer.schedule(
                self._watchdog_handler,
                str(self.config_path.parent),
                recursive=False
            )
            self._observer.start()
            logger.debug("Started config file watcher using file system notifications (watchdog)")
        except Exception as e:
            logger.warning("Failed to start watchdog observer: %s. Falling back to polling mode.", e)
            self._observer = None
            self._watchdog_handler = None
            logger.debug("Using polling mode (interval: %.1fs)", poll_interval)

        # Start the main watch loop
        self._watch_task = asyncio.create_task(self._watch_loop(poll_interval))

    async def stop_watching(self) -> None:
        """Stop watching the config file."""
        if not self._watch_task:
            return

        self._shutdown_event.set()
        self._reload_event.set()  # Wake up the watch loop
        self._watch_task.cancel()

        try:
            await self._watch_task
        except asyncio.CancelledError:
            pass

        # Stop watchdog observer if running
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=1.0)
            self._observer = None
            self._watchdog_handler = None

        self._watch_task = None
        logger.debug("Stopped config file watcher")

    def ignore_next_change(self) -> None:
        """Tell the reloader to ignore the next file change.

        This is useful when we're making programmatic changes to the config
        file and don't want to trigger a reload from our own changes.
        """
        self._ignore_next_change = True
        logger.debug("Will ignore next config file change")

    def update_cached_config(self, config: MaggConfig) -> None:
        """Update the cached config after a programmatic save.

        This keeps our internal state in sync when config is saved programmatically.
        """
        self._last_config = config

    def get_cached_config(self) -> MaggConfig | None:
        """Get the cached configuration if available.

        Returns:
            The cached config or None if no config has been loaded yet.
        """
        return self._last_config

    async def _watch_loop(self, poll_interval: float) -> None:
        """Main watch loop that handles both watchdog and polling modes."""
        try:
            # Initialize with current state
            if self.config_path.exists():
                self._last_mtime = self.config_path.stat().st_mtime
                self._last_config = self._load_config()

            while not self._shutdown_event.is_set():
                try:
                    if self._observer:
                        # Wait for reload event from watchdog
                        try:
                            await asyncio.wait_for(
                                self._reload_event.wait(),
                                timeout=60.0  # Wake up periodically to check shutdown
                            )
                            self._reload_event.clear()

                            if not self._shutdown_event.is_set():
                                # Small delay to debounce multiple rapid changes
                                await asyncio.sleep(0.1)
                                await self._check_for_changes()
                        except asyncio.TimeoutError:
                            # Just checking shutdown event periodically
                            pass
                    else:
                        await asyncio.sleep(poll_interval)
                        await self._check_for_changes()
                except Exception as e:
                    logger.error("Error in config watch loop: %s", e)

        except asyncio.CancelledError:
            logger.debug("Config watch loop cancelled")
            raise

    async def _check_for_changes(self) -> None:
        """Check if the config file has changed and trigger reload if needed."""
        if not self.config_path.exists():
            if self._last_mtime is not None:
                logger.warning("Config file disappeared: %s", self.config_path)
                self._last_mtime = None
            return

        current_mtime = self.config_path.stat().st_mtime

        # First time seeing the file
        if self._last_mtime is None:
            logger.debug("Config file appeared: %s", self.config_path)
            self._last_mtime = current_mtime
            self._last_config = self._load_config()
            return

        if current_mtime > self._last_mtime:
            if self._ignore_next_change:
                logger.debug("Ignoring config file change (internal modification)")
                self._ignore_next_change = False
                self._last_mtime = current_mtime
                return

            logger.debug("Config file changed, reloading...")
            await self.reload_config()
            self._last_mtime = current_mtime

    async def reload_config(self) -> ConfigChange | None:
        """Reload the configuration and detect changes.

        Returns:
            ConfigChange object if changes were detected, None otherwise
        """
        async with self._reload_lock:
            try:
                # Load new config
                new_config = self._load_config()
                if new_config is None:
                    logger.error("Failed to load new config")
                    return None

                # Get old config (use empty config if first load)
                old_config = self._last_config or MaggConfig()

                # Detect changes
                change = self._detect_changes(old_config, new_config)

                if change.has_changes:
                    logger.info(change.summarize())

                    # Validate new config before applying
                    if not self._validate_config(new_config):
                        logger.error("New config validation failed, not applying changes")
                        return None

                    # Call the reload callback
                    await self.reload_callback(change)

                    # Update last config only after successful reload
                    self._last_config = new_config

                else:
                    logger.debug("Config reloaded, no changes detected")
                    self._last_config = new_config

                return change

            except Exception as e:
                logger.error("Error reloading config: %s", e)
                return None

    def _load_config(self) -> MaggConfig | None:
        """Load configuration from disk."""
        try:
            with self.config_path.open('r') as f:
                data = json.load(f)

            servers = {}
            for name, server_data in data.get('servers', {}).items():
                try:
                    server_data['name'] = name
                    servers[name] = ServerConfig.model_validate(server_data)
                except Exception as e:
                    logger.error("Error loading server '%s': %s", name, e)
                    continue

            config = MaggConfig()
            config.servers = servers
            return config

        except Exception as e:
            logger.error("Error loading config file: %s", e)
            return None

    def _detect_changes(self, old_config: MaggConfig, new_config: MaggConfig) -> ConfigChange:
        """Detect changes between two configurations."""
        change = ConfigChange(old_config=old_config, new_config=new_config)

        old_servers = old_config.servers
        new_servers = new_config.servers

        # Find added servers
        for name in new_servers:
            if name not in old_servers:
                change.server_changes.append(ServerChange(
                    name=name,
                    action='add',
                    new_config=new_servers[name]
                ))

        # Find removed servers
        for name in old_servers:
            if name not in new_servers:
                change.server_changes.append(ServerChange(
                    name=name,
                    action='remove',
                    old_config=old_servers[name]
                ))

        # Find modified servers
        for name in old_servers:
            if name in new_servers:
                old_server = old_servers[name]
                new_server = new_servers[name]

                # Check if enabled state changed
                if old_server.enabled != new_server.enabled:
                    action = 'enable' if new_server.enabled else 'disable'
                    change.server_changes.append(ServerChange(
                        name=name,
                        action=action,
                        old_config=old_server,
                        new_config=new_server
                    ))
                # Check if other properties changed
                elif self._server_config_changed(old_server, new_server):
                    change.server_changes.append(ServerChange(
                        name=name,
                        action='update',
                        old_config=old_server,
                        new_config=new_server
                    ))

        return change

    def _server_config_changed(self, old: ServerConfig, new: ServerConfig) -> bool:
        """Check if server configuration has changed (excluding enabled state)."""
        # Compare relevant fields
        fields_to_check = [
            'source', 'prefix', 'command', 'args', 'uri',
            'env', 'cwd', 'transport'
        ]

        for field in fields_to_check:
            if getattr(old, field) != getattr(new, field):
                return True

        return False

    def _validate_config(self, config: MaggConfig) -> bool:
        """Validate that the configuration is valid."""
        try:
            for name, server in config.servers.items():
                if not server.command and not server.uri:
                    logger.error("Server '%s' has neither command nor uri", name)
                    return False

            return True

        except Exception as e:
            logger.error("Config validation error: %s", e)
            return False


class ReloadManager:
    """Manages configuration reloading for ConfigManager."""

    def __init__(self, config_manager: 'ConfigManager'):
        """Initialize the reload manager.

        Args:
            config_manager: The ConfigManager instance to manage reloading for
        """
        from .settings import ConfigManager
        self.config_manager: ConfigManager = config_manager
        self._config_reloader: ConfigReloader | None = None
        self._reload_callback: ReloadCallback | None = None

    @property
    def cached_config(self) -> MaggConfig | None:
        """Get the cached configuration if available."""
        if self._config_reloader:
            return self._config_reloader._last_config
        return None

    async def setup(self, reload_callback: ReloadCallback) -> None:
        """Setup config file watching with a callback.

        Args:
            reload_callback: Async callback to handle config changes
        """
        self._reload_callback = reload_callback
        config = self.config_manager.load_config()

        if config.auto_reload and not self._config_reloader:
            if self.config_manager.config_path.exists():
                self._config_reloader = ConfigReloader(
                    config_path=self.config_manager.config_path,
                    reload_callback=reload_callback
                )
                await self._config_reloader.start_watching(poll_interval=config.reload_poll_interval)

    async def stop(self) -> None:
        """Stop config file watching."""
        if self._config_reloader:
            await self._config_reloader.stop_watching()
            self._config_reloader = None

    async def reload(self) -> bool:
        """Manually trigger a configuration reload.

        Returns:
            True if reload was successful, False otherwise
        """
        if not self._reload_callback:
            logger.error("No reload callback configured")
            return False

        if not self._config_reloader:
            if not self.config_manager.config_path.exists():
                logger.error("Config file does not exist: %s", self.config_manager.config_path)
                return False

            config = self.config_manager.load_config()
            reloader = ConfigReloader(
                config_path=self.config_manager.config_path,
                reload_callback=self._reload_callback
            )
            change = await reloader.reload_config()
            return change is not None
        else:
            # Use existing reloader
            change = await self._config_reloader.reload_config()
            return change is not None

    def ignore_next_change(self) -> None:
        """Tell the reloader to ignore the next file change."""
        if self._config_reloader:
            self._config_reloader.ignore_next_change()

    def update_cached_config(self, config: MaggConfig) -> None:
        """Update the cached config after a programmatic save."""
        if self._config_reloader:
            self._config_reloader.update_cached_config(config)
