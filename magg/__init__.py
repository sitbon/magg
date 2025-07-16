"""Magg - MCP Aggregator

A self-aware MCP server that manages and aggregates other MCP tools and servers.
"""
from importlib import metadata

try:
    __version__ = metadata.version("magg")
except metadata.PackageNotFoundError:
    __version__ = "unknown"

del metadata

# Export main components
from .client import MaggClient
from .messaging import MaggMessageHandler, MessageRouter, ServerMessageCoordinator

__all__ = [
    "MaggClient",
    "MaggMessageHandler",
    "MessageRouter",
    "ServerMessageCoordinator",
]
