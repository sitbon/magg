#!/usr/bin/env python3
"""Demo script to demonstrate config reloading functionality."""
import asyncio
import json
import os
import signal
import sys
from pathlib import Path
import logging

# Add magg to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from magg.server.server.server import MaggServer
from magg.server.runner import MaggRunner
from magg import process

process.setup(MAGG_LOG_LEVEL="INFO")
logger = logging.getLogger(__name__)


async def demo_config_reload():
    """Demonstrate config reloading with file watching."""
    config_path = Path(".magg") / "config.json"

    logger.setLevel(logging.INFO)
    logger.info("Starting Magg server with config reloading enabled")
    logger.info("Config path: %s", config_path)
    logger.info("You can:")
    logger.info("  1. Modify the config file to see automatic reload")
    logger.info("  2. Send SIGHUP signal to trigger reload: kill -HUP %d", os.getpid())
    logger.info("  3. Use the magg_reload_config tool via MCP client")
    logger.info("")
    logger.info("Press Ctrl+C to stop")

    # Create runner with signal handling
    runner = MaggRunner(config_path)

    try:
        # Run the server
        await runner.run_http("localhost", 8000)
    except KeyboardInterrupt:
        logger.info("Shutting down...")


async def demo_manual_reload():
    """Demonstrate manual config reload."""
    config_path = Path.home() / ".magg" / "config.json"

    logger.info("Demonstrating manual config reload")

    server = MaggServer(str(config_path), enable_config_reload=False)
    async with server:
        # Show current servers
        logger.info("Current servers:")
        for name, srv in server.config.servers.items():
            logger.info("  - %s (%s)", name, "enabled" if srv.enabled else "disabled")

        # Simulate config change
        logger.info("\nSimulating config file change...")
        if config_path.exists():
            # Load current config
            with open(config_path) as f:
                config_data = json.load(f)

            # Add a demo server
            config_data["servers"]["demo-server"] = {
                "source": "https://example.com/demo",
                "command": "echo",
                "args": ["Demo server"],
                "enabled": True
            }

            # Save modified config
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            logger.info("Added 'demo-server' to config")

        # Trigger manual reload
        logger.info("\nTriggering manual reload...")
        success = await server.reload_config()

        if success:
            logger.info("Reload successful!")
            logger.info("\nServers after reload:")
            for name, srv in server.config.servers.items():
                logger.info("  - %s (%s)", name, "enabled" if srv.enabled else "disabled")
        else:
            logger.error("Reload failed!")

        # Clean up demo server
        if "demo-server" in config_data["servers"]:
            del config_data["servers"]["demo-server"]
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)
            logger.info("\nCleaned up demo-server from config")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Demo config reloading")
    parser.add_argument(
        "--mode",
        choices=["auto", "manual"],
        default="auto",
        help="Demo mode: auto (file watching + SIGHUP) or manual"
    )

    args = parser.parse_args()

    if args.mode == "auto":
        asyncio.run(demo_config_reload())
    else:
        asyncio.run(demo_manual_reload())


if __name__ == "__main__":
    main()
