#!/usr/bin/env python3
"""Bump version across all Sage files.

Usage:
    python scripts/bump_version.py 3.2.0
    python scripts/bump_version.py --check  # Show current versions
"""

import json
import re
import sys
from pathlib import Path

# Root of the repo
ROOT = Path(__file__).parent.parent

# Files that contain version strings
VERSION_FILES = {
    "pyproject.toml": {
        "pattern": r'^version = "[^"]+"',
        "replacement": 'version = "{version}"',
    },
    "sage/__init__.py": {
        "pattern": r'^__version__ = "[^"]+"',
        "replacement": '__version__ = "{version}"',
    },
    ".claude-plugin/plugin.json": {
        "type": "json",
        "key": "version",
    },
    ".claude-plugin/marketplace.json": {
        "type": "json",
        "key": ["plugins", 0, "version"],
    },
    "CLAUDE.md": {
        "pattern": r'\*\*Current version:\*\* v[0-9]+\.[0-9]+\.[0-9]+',
        "replacement": "**Current version:** v{version}",
    },
}


def get_current_versions() -> dict[str, str]:
    """Get current version from each file."""
    versions = {}

    for file, config in VERSION_FILES.items():
        path = ROOT / file
        if not path.exists():
            versions[file] = "NOT FOUND"
            continue

        content = path.read_text()

        if config.get("type") == "json":
            data = json.loads(content)
            key = config["key"]
            if isinstance(key, list):
                val = data
                for k in key:
                    val = val[k]
                versions[file] = val
            else:
                versions[file] = data.get(key, "NOT FOUND")
        else:
            match = re.search(config["pattern"], content, re.MULTILINE)
            if match:
                # Extract version number from match
                ver_match = re.search(r'[0-9]+\.[0-9]+\.[0-9]+', match.group())
                versions[file] = ver_match.group() if ver_match else "PARSE ERROR"
            else:
                versions[file] = "NOT FOUND"

    return versions


def bump_version(new_version: str) -> list[str]:
    """Update version in all files. Returns list of updated files."""
    updated = []

    for file, config in VERSION_FILES.items():
        path = ROOT / file
        if not path.exists():
            print(f"  SKIP {file} (not found)")
            continue

        content = path.read_text()

        if config.get("type") == "json":
            data = json.loads(content)
            key = config["key"]
            if isinstance(key, list):
                # Navigate to nested key
                obj = data
                for k in key[:-1]:
                    obj = obj[k]
                obj[key[-1]] = new_version
            else:
                data[key] = new_version
            new_content = json.dumps(data, indent=2) + "\n"
        else:
            replacement = config["replacement"].format(version=new_version)
            new_content = re.sub(config["pattern"], replacement, content, flags=re.MULTILINE)

        if new_content != content:
            path.write_text(new_content)
            updated.append(file)
            print(f"  OK   {file} -> {new_version}")
        else:
            print(f"  SAME {file}")

    return updated


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/bump_version.py <version>")
        print("       python scripts/bump_version.py --check")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "--check":
        print("Current versions:")
        print("-" * 50)
        versions = get_current_versions()
        for file, ver in versions.items():
            print(f"  {file}: {ver}")

        unique = set(versions.values()) - {"NOT FOUND", "PARSE ERROR"}
        if len(unique) == 1:
            print(f"\n✓ All versions in sync: {unique.pop()}")
        else:
            print(f"\n✗ Versions out of sync: {unique}")
            sys.exit(1)
    else:
        # Validate version format
        if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+$', arg):
            print(f"Invalid version format: {arg}")
            print("Expected: X.Y.Z (e.g., 3.2.0)")
            sys.exit(1)

        print(f"Bumping to version {arg}...")
        print("-" * 50)
        updated = bump_version(arg)
        print("-" * 50)
        print(f"Updated {len(updated)} file(s)")

        if updated:
            print("\nNext steps:")
            print(f"  git add {' '.join(updated)}")
            print(f"  git commit -m 'chore: bump version to {arg}'")


if __name__ == "__main__":
    main()
