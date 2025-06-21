"""URI utilities for MAGG - handles URI parsing and directory extraction."""

from pathlib import Path
from urllib.parse import urlparse, unquote
import os


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


def is_subdirectory(child: Path, parent: Path) -> bool:
    """Check if child is a subdirectory of parent.

    Args:
        child: Potential subdirectory path
        parent: Parent directory path

    Returns:
        True if child is same as or subdirectory of parent
    """
    try:
        # Resolve to absolute paths
        child_abs = child.resolve()
        parent_abs = parent.resolve()

        # Check if child is same as or starts with parent
        return child_abs == parent_abs or parent_abs in child_abs.parents
    except (OSError, RuntimeError):
        # Path resolution failed
        return False


def get_project_root() -> Path:
    """Get the current project root (where .magg directory is)."""
    return Path.cwd()


def validate_working_directory(working_dir: Path | str | None, source_uri: str | None) -> tuple[Path | None, str | None]:
    """Validate and normalize working directory for a server.

    Args:
        working_dir: Proposed working directory (or None)
        source_uri: URI of the source (or None)

    Returns:
        Tuple of (normalized_path or None, error_message or None)
    """
    project_root = get_project_root()

    # Parse source URI to get source directory
    source_dir = extract_directory_from_uri(source_uri) if source_uri else None

    if working_dir is None:
        # No working_dir provided - try to use source directory
        if source_dir is None:
            return None, "Working directory required for remote sources"

        # Use source directory as working directory
        working_dir = source_dir
    else:
        # Normalize the provided path
        working_dir = Path(working_dir)

    # Make absolute if relative
    if not working_dir.is_absolute():
        working_dir = project_root / working_dir

    # Resolve to canonical path
    try:
        working_dir = working_dir.resolve()
    except (OSError, RuntimeError):
        return None, f"Invalid working directory: {working_dir}"

    # Check that it exists
    if not working_dir.exists():
        return None, f"Working directory does not exist: {working_dir}"

    if not working_dir.is_dir():
        return None, f"Working directory is not a directory: {working_dir}"

    # Check that it's not the exact project root
    if working_dir == project_root:
        return None, "Working directory cannot be the project root"

    # If source has a directory, validate relationship
    if source_dir is not None:
        source_dir_abs = source_dir.resolve()
        if not is_subdirectory(working_dir, source_dir_abs):
            return None, f"Working directory must be within source directory: {source_dir_abs}"

    return working_dir, None
