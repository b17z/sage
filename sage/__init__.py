"""Sage: Research orchestration layer for Agent Skills."""

from __future__ import annotations

import json
import time
from pathlib import Path

__version__ = "3.0.0"

# Branded types for type-safe IDs
from sage.types import CheckpointId, KnowledgeId, SkillName, TaskId, TemplateName

__all__ = [
    "__version__",
    "CheckpointId",
    "KnowledgeId",
    "TaskId",
    "SkillName",
    "TemplateName",
    "check_for_updates",
]

# Cache duration: 24 hours
_UPDATE_CHECK_CACHE_SECONDS = 86400
_PYPI_URL = "https://pypi.org/pypi/claude-sage/json"


def _get_cache_path() -> Path:
    """Get path to version check cache file."""
    from sage.config import SAGE_DIR
    return SAGE_DIR / ".version_cache.json"


def _read_cache() -> dict | None:
    """Read cached version check result."""
    cache_path = _get_cache_path()
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text())
        # Check if cache is still valid
        if time.time() - data.get("checked_at", 0) < _UPDATE_CHECK_CACHE_SECONDS:
            return data
    except Exception:
        pass
    return None


def _write_cache(latest_version: str) -> None:
    """Write version check result to cache."""
    cache_path = _get_cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "latest_version": latest_version,
            "checked_at": time.time(),
        }))
    except Exception:
        pass  # Cache write failure is not critical


def check_for_updates() -> tuple[bool, str | None]:
    """Check if a newer version is available on PyPI.

    Returns:
        Tuple of (update_available, latest_version).
        Returns (False, None) if check fails or is cached as current.
    """
    # Check cache first
    cached = _read_cache()
    if cached:
        latest = cached.get("latest_version")
        if latest and latest != __version__:
            return True, latest
        return False, None

    # Fetch from PyPI
    try:
        import urllib.request
        with urllib.request.urlopen(_PYPI_URL, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            latest = data.get("info", {}).get("version")
            if latest:
                _write_cache(latest)
                if latest != __version__:
                    return True, latest
    except Exception:
        pass  # Network failure - fail silently

    return False, None
