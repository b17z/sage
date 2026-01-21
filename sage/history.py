"""History logging for Sage skills.

Append-only JSONL logs for tracking interactions, costs, and analytics.
"""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sage.config import get_sage_skill_path


@dataclass(frozen=True)
class HistoryEntry:
    """Immutable record of a single interaction."""

    ts: str
    type: str  # "ask", "research", "chat"
    query: str
    model: str
    tokens_in: int
    tokens_out: int
    searches: int
    cost: float
    response: str | None = None  # The actual response content
    cache_hits: int = 0
    depth: str | None = None
    session: str | None = None
    turns: int | None = None  # for chat sessions


def create_entry(
    entry_type: str,
    query: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    searches: int = 0,
    cache_hits: int = 0,
    response: str | None = None,
    depth: str | None = None,
    session: str | None = None,
    turns: int | None = None,
) -> HistoryEntry:
    """Create a new history entry with current timestamp."""
    # Estimate cost (rough approximation)
    # Claude Sonnet: $3/M input, $15/M output
    # Cache reads: $0.30/M
    input_cost = (tokens_in - cache_hits) * 3.0 / 1_000_000
    cached_cost = cache_hits * 0.30 / 1_000_000
    output_cost = tokens_out * 15.0 / 1_000_000
    search_cost = searches * 0.01  # ~$0.01 per search
    total_cost = input_cost + cached_cost + output_cost + search_cost

    return HistoryEntry(
        ts=datetime.now(UTC).isoformat(),
        type=entry_type,
        query=query,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        searches=searches,
        cost=round(total_cost, 4),
        response=response,
        cache_hits=cache_hits,
        depth=depth,
        session=session,
        turns=turns,
    )


def get_history_path(skill_name: str) -> Path:
    """Get path to a skill's history file."""
    return get_sage_skill_path(skill_name) / "history.jsonl"


def append_entry(skill_name: str, entry: HistoryEntry) -> None:
    """Append an entry to a skill's history log."""
    path = get_history_path(skill_name)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict, removing None values
    data = {k: v for k, v in asdict(entry).items() if v is not None}

    with open(path, "a") as f:
        f.write(json.dumps(data) + "\n")
    # Restrict permissions - history may contain sensitive queries
    path.chmod(0o600)


def read_history(skill_name: str, limit: int | None = None) -> list[HistoryEntry]:
    """Read history entries for a skill, most recent first."""
    path = get_history_path(skill_name)
    if not path.exists():
        return []

    entries = []
    with open(path) as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                entries.append(HistoryEntry(**data))

    # Most recent first
    entries.reverse()

    if limit:
        entries = entries[:limit]

    return entries


def get_recent_context(skill_name: str, max_entries: int = 5) -> list[dict]:
    """Get recent history formatted for context injection."""
    entries = read_history(skill_name, limit=max_entries)
    return [{"query": e.query, "type": e.type, "ts": e.ts} for e in entries]


def calculate_usage(skill_name: str, days: int = 7) -> dict:
    """Calculate usage statistics for a skill over a time period."""
    entries = read_history(skill_name)
    if not entries:
        return {
            "tokens_in": 0,
            "tokens_out": 0,
            "searches": 0,
            "cost": 0.0,
            "cache_hits": 0,
            "entries": 0,
        }

    cutoff = datetime.now(UTC).timestamp() - (days * 86400)
    recent = [
        e
        for e in entries
        if datetime.fromisoformat(e.ts.replace("Z", "+00:00")).timestamp() > cutoff
    ]

    return {
        "tokens_in": sum(e.tokens_in for e in recent),
        "tokens_out": sum(e.tokens_out for e in recent),
        "searches": sum(e.searches for e in recent),
        "cost": round(sum(e.cost for e in recent), 2),
        "cache_hits": sum(e.cache_hits for e in recent),
        "entries": len(recent),
    }
