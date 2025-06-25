#!/usr/bin/env python3
"""Validate version for the "Manual Publish" workflow.

This script checks if the current version of the package is suitable for manual release.
- It should only allow pre-releases, post-releases, or dev releases.
- It will output a JSON object with the validation result.
- If the version is a regular release, it will exit with an error.
- If the version is suitable, it will exit with success.
- The script is intended to be run in a GitHub Actions workflow.
- It uses the `importlib.metadata` module to get the package version.
"""
import json
import sys
from importlib.metadata import version as get_version

from packaging.version import Version


def validate_version():
    """Validate that the current version is suitable for manual release."""
    try:
        version_str = get_version("magg")
        version = Version(version_str)
    except Exception as e:
        result = {
            "valid": False,
            "version": "unknown",
            "error": str(e),
            "message": f"Failed to get version: {e}"
        }
        print(json.dumps(result))
        sys.exit(1)

    # Check if it's a pre-release, post-release, or dev release
    is_prerelease = version.is_prerelease
    is_postrelease = version.is_postrelease
    is_devrelease = version.is_devrelease

    # Manual release should only handle pre/post/dev releases
    if not (is_prerelease or is_postrelease or is_devrelease):
        result = {
            "valid": False,
            "version": version_str,
            "error": "regular_release",
            "message": f"Version {version_str} is a regular release. Manual publish only supports pre-releases, post-releases, or dev releases.",
            "is_prerelease": False,
            "is_postrelease": False,
            "is_devrelease": False
        }
        print(json.dumps(result))
        sys.exit(1)

    # Build result
    types = []
    if is_prerelease:
        types.append("pre-release")
    if is_postrelease:
        types.append("post-release")
    if is_devrelease:
        types.append("dev release")

    result = {
        "valid": True,
        "version": version_str,
        "message": f"Valid {' + '.join(types)}: {version_str}",
        "is_prerelease": is_prerelease,
        "is_postrelease": is_postrelease,
        "is_devrelease": is_devrelease,
        "types": types
    }

    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    validate_version()
