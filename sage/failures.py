"""Failure memory for Sage.

Tracks what didn't work and why to avoid repeating mistakes.
Failures are stored in .sage/failures/ as markdown files with YAML frontmatter.

Example failure:
    ---
    id: jwt-refresh-loop
    approach: "Using localStorage for refresh tokens"
    keywords: [jwt, refresh, token, auth]
    related_to: [auth-patterns, jwt-security]
    ---

    ## Why it failed
    XSS vulnerability - localStorage is accessible to any JS on the page.

    ## Learned
    Use httpOnly cookies for refresh tokens instead.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from sage.config import SAGE_DIR, detect_project_root

logger = logging.getLogger(__name__)


# Global failures directory
FAILURES_DIR = SAGE_DIR / "failures"


def _get_failures_dir(project_path: Path | None = None) -> Path:
    """Get the failures directory, preferring project-local.

    Args:
        project_path: Optional project path

    Returns:
        Path to failures directory
    """
    if project_path:
        # Always use project_path if specified
        return project_path / ".sage" / "failures"

    # Auto-detect project
    detected = detect_project_root()
    if detected:
        project_sage = detected / ".sage"
        if project_sage.exists():
            return project_sage / "failures"

    # Fall back to global
    return FAILURES_DIR


def ensure_failures_dir(project_path: Path | None = None) -> Path:
    """Ensure failures directory exists.

    Args:
        project_path: Optional project path

    Returns:
        Path to the failures directory
    """
    # If project_path specified, always use it (create .sage if needed)
    if project_path:
        failures_dir = project_path / ".sage" / "failures"
    else:
        failures_dir = _get_failures_dir(project_path)
    failures_dir.mkdir(parents=True, exist_ok=True)
    return failures_dir


@dataclass(frozen=True)
class Failure:
    """A record of something that didn't work."""

    id: str  # Unique identifier (kebab-case)
    approach: str  # What was tried
    why_failed: str  # Why it didn't work
    learned: str  # What to do instead
    keywords: tuple[str, ...]  # Trigger keywords for matching
    related_to: tuple[str, ...] = ()  # Related checkpoint/knowledge IDs
    added: str = ""  # ISO date when added
    project: str | None = None  # Project scope


def _sanitize_id(raw_id: str) -> str:
    """Sanitize an ID to prevent path traversal attacks."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_id).strip("-")
    return sanitized or "unnamed"


def _failure_to_markdown(failure: Failure) -> str:
    """Convert a Failure to Markdown with YAML frontmatter."""
    frontmatter = {
        "id": failure.id,
        "type": "failure",
        "approach": failure.approach,
        "keywords": list(failure.keywords),
        "related_to": list(failure.related_to) if failure.related_to else None,
        "added": failure.added,
        "project": failure.project,
    }
    # Remove None values
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None}

    fm_yaml = yaml.safe_dump(
        frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True
    )

    body = f"""## Why it failed
{failure.why_failed}

## Learned
{failure.learned}
"""

    return f"---\n{fm_yaml}---\n\n{body}"


def _markdown_to_failure(content: str) -> Failure | None:
    """Parse a Markdown failure file into a Failure object."""
    try:
        if not content.startswith("---"):
            return None

        end_idx = content.find("---", 3)
        if end_idx == -1:
            return None

        fm_text = content[3:end_idx].strip()
        body = content[end_idx + 3:].strip()

        fm = yaml.safe_load(fm_text) or {}

        # Parse body sections
        why_failed = ""
        learned = ""
        current_section = None
        section_lines: list[str] = []

        for line in body.split("\n"):
            if line.startswith("## "):
                # Save previous section
                if current_section == "why_it_failed":
                    why_failed = "\n".join(section_lines).strip()
                elif current_section == "learned":
                    learned = "\n".join(section_lines).strip()

                # Start new section
                section_name = line[3:].strip().lower().replace(" ", "_")
                current_section = section_name
                section_lines = []
            else:
                section_lines.append(line)

        # Save last section
        if current_section == "why_it_failed":
            why_failed = "\n".join(section_lines).strip()
        elif current_section == "learned":
            learned = "\n".join(section_lines).strip()

        return Failure(
            id=fm.get("id", ""),
            approach=fm.get("approach", ""),
            why_failed=why_failed,
            learned=learned,
            keywords=tuple(fm.get("keywords", [])),
            related_to=tuple(fm.get("related_to", [])),
            added=fm.get("added", ""),
            project=fm.get("project"),
        )
    except (yaml.YAMLError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse failure: {e}")
        return None


def save_failure(
    failure_id: str,
    approach: str,
    why_failed: str,
    learned: str,
    keywords: list[str],
    related_to: list[str] | None = None,
    project_path: Path | None = None,
) -> Failure:
    """Save a new failure record.

    Args:
        failure_id: Unique identifier (kebab-case)
        approach: What was tried
        why_failed: Why it didn't work
        learned: What to do instead
        keywords: Trigger keywords for matching
        related_to: Related checkpoint/knowledge IDs
        project_path: Optional project path

    Returns:
        The saved Failure object
    """
    from sage.atomic import atomic_write_text

    failures_dir = ensure_failures_dir(project_path)

    safe_id = _sanitize_id(failure_id)
    added = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Detect project name
    project_name = None
    if project_path:
        project_name = project_path.name
    else:
        detected = detect_project_root()
        if detected:
            project_name = detected.name

    failure = Failure(
        id=safe_id,
        approach=approach,
        why_failed=why_failed,
        learned=learned,
        keywords=tuple(keywords),
        related_to=tuple(related_to) if related_to else (),
        added=added,
        project=project_name,
    )

    # Generate filename with timestamp for uniqueness
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"{ts}_{safe_id}.md"
    file_path = failures_dir / filename

    content = _failure_to_markdown(failure)

    result = atomic_write_text(file_path, content, mode=0o600)
    if result.is_err():
        raise OSError(f"Failed to save failure: {result.unwrap_err().message}")

    # Add embedding for semantic search
    _add_failure_embedding(safe_id, f"{approach} {why_failed} {learned}")

    logger.info(f"Saved failure: {safe_id}")
    return failure


def load_failures(project_path: Path | None = None) -> list[Failure]:
    """Load all failure records.

    Args:
        project_path: Optional project path

    Returns:
        List of Failure objects, most recent first
    """
    failures_dir = _get_failures_dir(project_path)

    if not failures_dir.exists():
        return []

    failures = []
    for file_path in sorted(failures_dir.glob("*.md"), reverse=True):
        try:
            content = file_path.read_text()
            failure = _markdown_to_failure(content)
            if failure:
                failures.append(failure)
        except OSError as e:
            logger.warning(f"Failed to read failure file {file_path}: {e}")

    return failures


def recall_failures(
    query: str,
    limit: int = 3,
    project_path: Path | None = None,
) -> list[Failure]:
    """Recall failures relevant to a query using semantic search.

    Args:
        query: Query text to match against
        limit: Maximum number of failures to return
        project_path: Optional project path

    Returns:
        List of relevant Failure objects
    """
    failures = load_failures(project_path)

    if not failures:
        return []

    # Try semantic search if embeddings available
    try:
        from sage import embeddings

        if embeddings.is_available():
            similarities = _get_failure_similarities(query)
            if similarities:
                # Score and rank failures
                scored: list[tuple[Failure, float]] = []
                for f in failures:
                    # Combine embedding similarity with keyword matching
                    emb_score = similarities.get(f.id, 0.0)
                    kw_score = _keyword_score(f, query)
                    combined = 0.7 * emb_score + 0.3 * kw_score
                    scored.append((f, combined))

                # Sort by score and filter
                scored.sort(key=lambda x: x[1], reverse=True)
                threshold = 0.3  # Minimum score to include
                return [f for f, score in scored[:limit] if score >= threshold]
    except Exception as e:
        logger.debug(f"Semantic failure search failed, using keyword: {e}")

    # Fall back to keyword matching
    return _keyword_recall(failures, query, limit)


def _keyword_score(failure: Failure, query: str) -> float:
    """Score a failure against a query using keyword matching.

    Returns score in 0-1 range.
    """
    query_lower = query.lower()
    score = 0

    for kw in failure.keywords:
        kw_lower = kw.lower()
        if kw_lower in query_lower:
            if re.search(rf"\b{re.escape(kw_lower)}\b", query_lower):
                score += 2  # Exact word match
            else:
                score += 1  # Partial match

    # Normalize to 0-1 range (max realistic score ~6)
    return min(score / 6.0, 1.0)


def _keyword_recall(
    failures: list[Failure],
    query: str,
    limit: int,
) -> list[Failure]:
    """Recall failures using keyword matching only."""
    scored = [(f, _keyword_score(f, query)) for f in failures]
    scored.sort(key=lambda x: x[1], reverse=True)
    threshold = 0.2
    return [f for f, score in scored[:limit] if score >= threshold]


# =============================================================================
# Embedding Support
# =============================================================================


def _get_failure_embedding_store():
    """Load the failure embedding store."""
    from sage import embeddings

    path = SAGE_DIR / "embeddings" / "failures.pkl"
    result = embeddings.load_embeddings(path)
    if result.is_err():
        return embeddings.EmbeddingStore.empty()
    return result.unwrap()


def _save_failure_embedding_store(store) -> bool:
    """Save the failure embedding store."""
    from sage import embeddings

    path = SAGE_DIR / "embeddings" / "failures.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)
    result = embeddings.save_embeddings(path, store)
    return result.is_ok()


def _add_failure_embedding(failure_id: str, content: str) -> bool:
    """Generate and store embedding for a failure."""
    from sage import embeddings

    if not embeddings.is_available():
        return False

    try:
        result = embeddings.get_embedding(content)
        if result.is_err():
            return False

        embedding = result.unwrap()
        store = _get_failure_embedding_store()
        store = store.add(failure_id, embedding)
        return _save_failure_embedding_store(store)
    except Exception as e:
        logger.debug(f"Failed to add failure embedding: {e}")
        return False


def _get_failure_similarities(query: str) -> dict[str, float]:
    """Get embedding similarities for all failures."""
    from sage import embeddings

    if not embeddings.is_available():
        return {}

    try:
        result = embeddings.get_query_embedding(query)
        if result.is_err():
            return {}

        query_embedding = result.unwrap()
        store = _get_failure_embedding_store()

        if len(store) == 0:
            return {}

        similar_items = embeddings.find_similar(query_embedding, store, threshold=0.0)
        return {item.id: item.score for item in similar_items}
    except Exception:
        return {}


# =============================================================================
# Utility Functions
# =============================================================================


def list_failures(
    project_path: Path | None = None,
    limit: int = 20,
) -> list[Failure]:
    """List failures, most recent first.

    Args:
        project_path: Optional project path
        limit: Maximum number to return

    Returns:
        List of Failure objects
    """
    failures = load_failures(project_path)
    return failures[:limit]


def delete_failure(
    failure_id: str,
    project_path: Path | None = None,
) -> bool:
    """Delete a failure by ID.

    Args:
        failure_id: Failure ID (can be partial match)
        project_path: Optional project path

    Returns:
        True if deleted, False if not found
    """
    failures_dir = _get_failures_dir(project_path)

    if not failures_dir.exists():
        return False

    # Try exact match first, then partial
    for file_path in failures_dir.glob("*.md"):
        if failure_id in file_path.stem:
            try:
                file_path.unlink()
                logger.info(f"Deleted failure: {failure_id}")
                return True
            except OSError as e:
                logger.warning(f"Failed to delete failure {failure_id}: {e}")
                return False

    return False


def format_failure_for_context(failure: Failure, use_toon: bool = False) -> str:
    """Format a failure for context injection.

    Args:
        failure: The Failure to format
        use_toon: Use TOON-style compact format

    Returns:
        Formatted string
    """
    if use_toon:
        return f"""## {failure.id}
approach: {failure.approach}
failed: {failure.why_failed}
learned: {failure.learned}
"""

    return f"""## {failure.id}
**Approach:** {failure.approach}
**Why it failed:** {failure.why_failed}
**Learned:** {failure.learned}
"""
