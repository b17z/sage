"""Shared memory management for Sage.

Cross-skill insights that propagate to all skills.
"""

from datetime import datetime
from pathlib import Path

from sage.config import SHARED_MEMORY_PATH


def load_memory() -> str:
    """Load shared memory content."""
    if not SHARED_MEMORY_PATH.exists():
        return ""
    return SHARED_MEMORY_PATH.read_text()


def add_insight(insight: str) -> None:
    """Add an insight to shared memory."""
    SHARED_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Initialize if needed
    if not SHARED_MEMORY_PATH.exists():
        content = """# Shared Memory

Insights that inform all research skills.

---

"""
        SHARED_MEMORY_PATH.write_text(content)

    # Add the insight
    date = datetime.now().strftime("%Y-%m-%d")
    entry = f"- **[{date}]** {insight}\n"

    with open(SHARED_MEMORY_PATH, "a") as f:
        f.write(entry)


def count_insights() -> int:
    """Count insights in shared memory."""
    if not SHARED_MEMORY_PATH.exists():
        return 0

    content = SHARED_MEMORY_PATH.read_text()
    return len([l for l in content.split("\n") if l.strip().startswith("- ")])


def get_recent_insights(limit: int = 10) -> list[str]:
    """Get most recent insights."""
    if not SHARED_MEMORY_PATH.exists():
        return []

    content = SHARED_MEMORY_PATH.read_text()
    insights = [l.strip() for l in content.split("\n") if l.strip().startswith("- ")]

    # Most recent are at the end
    return insights[-limit:]
