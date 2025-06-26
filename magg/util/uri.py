"""URI utilities for Magg - handles URI parsing and directory extraction."""

from pathlib import Path
from urllib.parse import urlparse, unquote
import os

from .system import get_project_root, is_subdirectory

__all__ = "extract_directory_from_uri", "validate_working_directory"


def extract_directory_from_uri(uri: str) -> Path | None:
    """Extract a directory path from a URI.

    Handles:
    - file:// URIs -> direct path
    - GitHub URIs -> None (remote)
    - HTTP/HTTPS URIs -> None (remote)
    - Plain paths -> treat as file path

    Returns:
        Path object if local directory can be determined, None otherwise
    """
    # Parse the URI
    parsed = urlparse(uri)

    if parsed.scheme == 'file':
        # file:// URI - extract the path
        path = unquote(parsed.path)
        # Remove leading slash on Windows
        if os.name == 'nt' and path.startswith('/') and len(path) > 2 and path[2] == ':':
            path = path[1:]
        return Path(path)
    elif parsed.scheme in ('http', 'https', 'git', 'ssh'):
        # Remote URI - no local directory
        return None
    elif not parsed.scheme:
        # No scheme - treat as local path
        return Path(uri)
    else:
        # Unknown scheme
        return None


def validate_working_directory(cwd: Path | str | None, source_uri: str | None) -> tuple[Path | None, str | None]:
    """Validate and normalize working directory for a server.

    Args:
        cwd: Proposed working directory (or None)
        source_uri: URI of the source (or None)

    Returns:
        Tuple of (normalized_path or None, error_message or None)
    """
    if cwd is None:
        # No validation needed if no cwd provided
        return None, None

    project_root = get_project_root()

    # Normalize the provided path
    cwd = Path(cwd)

    # Make absolute if relative
    if not cwd.is_absolute():
        cwd = project_root / cwd

    # Resolve to canonical path
    try:
        cwd = cwd.resolve()
    except (OSError, RuntimeError):
        return None, f"Invalid working directory: {cwd}"

    # Check that it exists
    if not cwd.exists():
        return None, f"Working directory does not exist: {cwd}"

    if not cwd.is_dir():
        return None, f"Working directory is not a directory: {cwd}"

    # Check that it's not the exact project root
    if cwd == project_root:
        return None, "Working directory cannot be the project root"

    # If source has a local directory, validate relationship
    if source_uri:
        source_dir = extract_directory_from_uri(source_uri)
        if source_dir is not None:
            source_dir_abs = source_dir.resolve()
            if not is_subdirectory(cwd, source_dir_abs):
                return None, f"Working directory must be within source directory: {source_dir_abs}"

    return cwd, None
