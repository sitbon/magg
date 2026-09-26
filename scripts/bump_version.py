#!/usr/bin/env python3
"""Bump Magg's version, or check that the versions in the repo agree.

    scripts/bump_version.py minor      # major, minor, patch, or an explicit version like 1.3.0
    scripts/bump_version.py --check    # exit 1 if server.json doesn't match pyproject.toml

Bumping runs `uv version`, which updates pyproject.toml and re-locks uv.lock, then copies
the new version into server.json (its top-level version and each package version).
"""

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SERVER_JSON = ROOT / "server.json"

# Values `uv version --bump` accepts; anything else is passed as an explicit version
BUMPS = ("major", "minor", "patch", "stable", "alpha", "beta", "rc", "post", "dev")


def project_version() -> str:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def manifest_versions(manifest: dict) -> list[str]:
    return [manifest["version"], *(package["version"] for package in manifest.get("packages", []))]


def check() -> int:
    version = project_version()
    versions = manifest_versions(json.loads(SERVER_JSON.read_text()))

    if any(v != version for v in versions):
        print(
            f"server.json versions {versions} don't match pyproject.toml version {version}. "
            f"Run: scripts/bump_version.py {version}",
            file=sys.stderr,
        )
        return 1

    print(f"server.json matches pyproject.toml version {version}")
    return 0


def bump(value: str) -> int:
    args = ["--bump", value] if value in BUMPS else [value]
    subprocess.run(["uv", "version", "--no-sync", *args], cwd=ROOT, check=True)
    version = project_version()

    manifest = json.loads(SERVER_JSON.read_text())
    manifest["version"] = version
    for package in manifest.get("packages", []):
        package["version"] = version
    SERVER_JSON.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Updated server.json to {version}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("version", nargs="?", help=f"one of {', '.join(BUMPS)}, or an explicit version")
    group.add_argument("--check", action="store_true", help="only check that server.json matches pyproject.toml")
    args = parser.parse_args()

    return check() if args.check else bump(args.version)


if __name__ == "__main__":
    sys.exit(main())
