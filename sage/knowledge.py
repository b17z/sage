"""Knowledge recall system for Sage.

Automatically injects relevant knowledge snippets into context based on query matching.
Knowledge items are stored in ~/.sage/knowledge/ with keyword triggers.

When embeddings are available (sentence-transformers installed), uses semantic
similarity for recall with keyword matching as a fallback/boost.
"""

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from sage.config import SAGE_DIR, detect_project_root, get_sage_config
from sage.types import KnowledgeId

logger = logging.getLogger(__name__)


# Global fallback paths
KNOWLEDGE_DIR = SAGE_DIR / "knowledge"
KNOWLEDGE_INDEX = KNOWLEDGE_DIR / "index.yaml"


def _get_knowledge_dir(project_path: Path | None = None) -> Path:
    """Get the knowledge directory, preferring project-local.

    Knowledge is project-scoped so teams can share knowledge via git.

    Args:
        project_path: Optional project path to use

    Returns:
        Path to knowledge directory (project-local if available, else global)
    """
    if project_path:
        project_sage = project_path / ".sage"
        if project_sage.exists():
            return project_sage / "knowledge"

    # Auto-detect project
    detected = detect_project_root()
    if detected:
        project_sage = detected / ".sage"
        if project_sage.exists():
            return project_sage / "knowledge"

    # Fall back to global
    return KNOWLEDGE_DIR


def _get_knowledge_index(project_path: Path | None = None) -> Path:
    """Get the knowledge index file path, preferring project-local."""
    return _get_knowledge_dir(project_path) / "index.yaml"


# ============================================================================
# Knowledge Types
# ============================================================================

# Valid knowledge types
KNOWLEDGE_TYPES = ("knowledge", "preference", "todo", "reference")

# Type-specific recall thresholds (0-1 scale)
# These are multiplied by 10 internally when compared to scores
TYPE_THRESHOLDS: dict[str, float] = {
    "knowledge": 0.70,  # Standard query matching
    "preference": 0.30,  # Aggressive recall (user preferences)
    "todo": 0.40,  # Session-start + keyword match
    "reference": 0.80,  # Lower priority, on-demand
}

# Default threshold for unknown types
DEFAULT_TYPE_THRESHOLD = 0.70

# Max keyword score for normalization (keyword scoring typically gives 0-9)
# Used to normalize keyword scores to 0-1 range for hybrid scoring
MAX_KEYWORD_SCORE = 9.0


@dataclass(frozen=True)
class KnowledgeTriggers:
    """Trigger conditions for knowledge recall."""

    keywords: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()  # regex patterns


@dataclass(frozen=True)
class KnowledgeScope:
    """Scope restrictions for knowledge items."""

    skills: tuple[str, ...] = ()  # empty = all skills
    always: bool = False  # if True, always inject


@dataclass(frozen=True)
class KnowledgeMetadata:
    """Metadata about a knowledge item."""

    added: str  # ISO date
    source: str = ""  # where this came from
    tokens: int = 0  # estimated token count
    status: str = ""  # For todos: pending | done


@dataclass(frozen=True)
class KnowledgeItem:
    """A single knowledge item."""

    id: KnowledgeId
    file: str  # relative path from KNOWLEDGE_DIR
    triggers: KnowledgeTriggers
    scope: KnowledgeScope
    metadata: KnowledgeMetadata
    item_type: str = "knowledge"  # knowledge | preference | todo | reference
    content: str = ""  # loaded on demand


@dataclass
class RecallResult:
    """Result of knowledge recall."""

    items: list[KnowledgeItem]
    total_tokens: int

    @property
    def count(self) -> int:
        return len(self.items)


def ensure_knowledge_dir(project_path: Path | None = None) -> Path:
    """Ensure knowledge directory structure exists.

    Args:
        project_path: Optional project path for project-scoped knowledge

    Returns:
        Path to the knowledge directory that was ensured
    """
    knowledge_dir = _get_knowledge_dir(project_path)
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    (knowledge_dir / "global").mkdir(exist_ok=True)
    (knowledge_dir / "skills").mkdir(exist_ok=True)
    return knowledge_dir


# ============================================================================
# Index Cache (TTL + mtime validation)
# ============================================================================


@dataclass
class _IndexCache:
    """In-memory cache for the knowledge index.

    Uses TTL (time-to-live) and mtime validation for cache invalidation:
    - Cache expires after knowledge_cache_ttl_seconds
    - Cache invalidates if index file mtime changes (external edits)
    - Cache invalidates on any write operation via _invalidate_index_cache()
    """

    items: list["KnowledgeItem"] = field(default_factory=list)
    mtime: float = 0.0  # Index file mtime at load time
    loaded_at: float = 0.0  # Monotonic time of load

    def is_valid(self, ttl_seconds: float) -> bool:
        """Check if cache is still valid.

        Args:
            ttl_seconds: TTL from config

        Returns:
            True if cache is valid (not expired and mtime unchanged)
        """
        if not self.items and self.loaded_at == 0.0:
            # Empty cache that was never loaded
            return False

        # Check TTL expiry
        if time.monotonic() - self.loaded_at > ttl_seconds:
            return False

        # Check mtime (detect external edits)
        try:
            current_mtime = KNOWLEDGE_INDEX.stat().st_mtime
            if current_mtime != self.mtime:
                return False
        except OSError:
            # File doesn't exist or inaccessible - invalidate cache
            return False

        return True


# Global cache instance and lock
_index_cache = _IndexCache()
_index_cache_lock = threading.Lock()


def _invalidate_index_cache() -> None:
    """Invalidate the index cache.

    Call this after any write operation that modifies the index.
    Thread-safe.
    """
    global _index_cache
    with _index_cache_lock:
        _index_cache = _IndexCache()
    logger.debug("Knowledge index cache invalidated")


def _get_cached_index() -> list["KnowledgeItem"] | None:
    """Get cached index if valid.

    Returns:
        Cached items if cache is valid, None otherwise
    """
    config = get_sage_config()
    ttl = config.knowledge_cache_ttl_seconds

    with _index_cache_lock:
        if _index_cache.is_valid(ttl):
            logger.debug("Knowledge index cache hit")
            return _index_cache.items.copy()  # Return copy for safety

    return None


def _set_cached_index(items: list["KnowledgeItem"]) -> None:
    """Update the index cache.

    Args:
        items: Items to cache
    """
    global _index_cache

    try:
        mtime = KNOWLEDGE_INDEX.stat().st_mtime
    except OSError:
        mtime = 0.0

    with _index_cache_lock:
        _index_cache = _IndexCache(
            items=items.copy(),  # Store copy
            mtime=mtime,
            loaded_at=time.monotonic(),
        )
    logger.debug(f"Knowledge index cached: {len(items)} items")


# ============================================================================
# Embedding Support
# ============================================================================


def _get_embedding_store():
    """Load the knowledge embedding store (lazy import to avoid circular deps)."""
    from sage import embeddings

    path = embeddings.get_knowledge_embeddings_path()
    result = embeddings.load_embeddings(path)
    if result.is_err():
        logger.warning(f"Failed to load knowledge embeddings: {result.unwrap_err().message}")
        return embeddings.EmbeddingStore.empty()
    return result.unwrap()


def _save_embedding_store(store) -> bool:
    """Save the knowledge embedding store."""
    from sage import embeddings

    path = embeddings.get_knowledge_embeddings_path()
    embeddings.ensure_embeddings_dir()
    result = embeddings.save_embeddings(path, store)
    if result.is_err():
        logger.warning(f"Failed to save knowledge embeddings: {result.unwrap_err().message}")
        return False
    return True


def _add_embedding(knowledge_id: str, content: str) -> bool:
    """Generate and store embedding for a knowledge item.

    Args:
        knowledge_id: The knowledge item ID
        content: The content to embed

    Returns:
        True if embedding was added successfully
    """
    from sage import embeddings

    if not embeddings.is_available():
        logger.debug("Embeddings not available, skipping")
        return False

    result = embeddings.get_embedding(content)
    if result.is_err():
        logger.warning(f"Failed to generate embedding: {result.unwrap_err().message}")
        return False

    embedding = result.unwrap()
    store = _get_embedding_store()
    store = store.add(knowledge_id, embedding)
    return _save_embedding_store(store)


def _remove_embedding(knowledge_id: str) -> bool:
    """Remove embedding for a knowledge item.

    Args:
        knowledge_id: The knowledge item ID

    Returns:
        True if embedding was removed successfully
    """
    from sage import embeddings

    if not embeddings.is_available():
        return True  # Nothing to remove

    store = _get_embedding_store()
    store = store.remove(knowledge_id)
    return _save_embedding_store(store)


def _get_all_embedding_similarities(query: str) -> dict[str, float]:
    """Get embedding similarities for all knowledge items.

    Args:
        query: The query text

    Returns:
        Dict mapping knowledge_id to similarity score
    """
    from sage import embeddings

    if not embeddings.is_available():
        return {}

    # Get query embedding (with prefix if model requires it)
    result = embeddings.get_query_embedding(query)
    if result.is_err():
        return {}

    query_embedding = result.unwrap()
    store = _get_embedding_store()

    if len(store) == 0:
        return {}

    # Compute all similarities at once
    similar_items = embeddings.find_similar(query_embedding, store, threshold=0.0)

    return {item.id: item.score for item in similar_items}


def rebuild_all_embeddings() -> tuple[int, int]:
    """Rebuild embeddings for all knowledge items.

    Use after model change or to fix missing embeddings.

    Returns:
        Tuple of (success_count, failed_count)
    """
    from sage import embeddings

    if not embeddings.is_available():
        logger.warning("Embeddings not available")
        return 0, 0

    items = load_index()
    success = 0
    failed = 0

    # Load all content
    contents = []
    ids = []
    for item in items:
        loaded = load_knowledge_content(item)
        if loaded.content:
            contents.append(loaded.content)
            ids.append(item.id)
        else:
            failed += 1

    if not contents:
        return 0, failed

    # Batch embed all content
    result = embeddings.get_embeddings_batch(contents)
    if result.is_err():
        logger.error(f"Failed to batch embed: {result.unwrap_err().message}")
        return 0, len(items)

    batch_embeddings = result.unwrap()

    # Build new store
    store = embeddings.EmbeddingStore.empty()
    for i, item_id in enumerate(ids):
        store = store.add(item_id, batch_embeddings[i])
        success += 1

    _save_embedding_store(store)
    logger.info(f"Rebuilt {success} embeddings")
    return success, failed


# ============================================================================
# Knowledge Maintenance
# ============================================================================


@dataclass(frozen=True)
class KnowledgeMaintenanceResult:
    """Result of knowledge maintenance operation."""

    pruned_by_age: int = 0
    total_remaining: int = 0


def run_knowledge_maintenance(
    max_age_days: int | None = None,
    project_path: Path | None = None,
) -> KnowledgeMaintenanceResult:
    """Prune old knowledge items by metadata.added date.

    Note: Unlike checkpoints, knowledge items don't have a max_count cap
    because they are intentionally curated by users.

    Args:
        max_age_days: Override config knowledge_max_age_days (0 = never prune)
        project_path: Optional project path for project-scoped knowledge

    Returns:
        KnowledgeMaintenanceResult with counts of pruned and remaining items
    """
    from datetime import datetime, timedelta

    config = get_sage_config(project_path)

    if max_age_days is None:
        max_age_days = config.knowledge_max_age_days

    # If pruning disabled, return early
    if max_age_days == 0:
        items = load_index(bypass_cache=True, project_path=project_path)
        return KnowledgeMaintenanceResult(pruned_by_age=0, total_remaining=len(items))

    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=max_age_days)

    items = load_index(bypass_cache=True, project_path=project_path)
    if not items:
        return KnowledgeMaintenanceResult()

    to_keep = []
    to_prune = []

    for item in items:
        # Parse the added date from metadata
        try:
            if not item.metadata.added:
                # No date, keep it
                to_keep.append(item)
                continue

            # Try to parse ISO date (YYYY-MM-DD or full ISO datetime)
            added_str = item.metadata.added
            if "T" in added_str:
                added_date = datetime.fromisoformat(added_str.replace("Z", "+00:00"))
            else:
                added_date = datetime.fromisoformat(added_str)

            # Remove timezone info for comparison
            if added_date.tzinfo is not None:
                added_date = added_date.replace(tzinfo=None)

            if added_date < cutoff_date:
                to_prune.append(item)
            else:
                to_keep.append(item)

        except (ValueError, TypeError) as e:
            # Can't parse date, keep the item
            logger.warning(f"Can't parse date for {item.id}: {e}")
            to_keep.append(item)

    # Prune items
    knowledge_dir = _get_knowledge_dir(project_path)
    pruned_count = 0
    for item in to_prune:
        try:
            # Delete content file
            content_path = knowledge_dir / item.file
            if content_path.exists():
                content_path.unlink()

            # Remove embedding
            _remove_embedding(item.id)

            pruned_count += 1
            logger.info(f"Pruned old knowledge: {item.id}")

        except OSError as e:
            logger.warning(f"Failed to prune knowledge {item.id}: {e}")
            # Keep it in the index if we couldn't delete it
            to_keep.append(item)

    # Save updated index (only if we pruned something)
    if pruned_count > 0:
        save_index(to_keep, project_path=project_path)
        logger.info(f"Knowledge maintenance: pruned {pruned_count}, {len(to_keep)} remaining")

    return KnowledgeMaintenanceResult(
        pruned_by_age=pruned_count,
        total_remaining=len(to_keep),
    )


def load_index(
    bypass_cache: bool = False, project_path: Path | None = None
) -> list[KnowledgeItem]:
    """Load knowledge index from YAML.

    Uses TTL caching with mtime validation for performance.
    Cache is automatically invalidated on write operations.

    Args:
        bypass_cache: If True, skip cache and load from disk
        project_path: Optional project path for project-scoped knowledge

    Returns:
        List of KnowledgeItem objects
    """
    # Check cache first (unless bypassed)
    # Note: Cache is global, so project-scoped loads bypass cache for now
    if not bypass_cache and project_path is None:
        cached = _get_cached_index()
        if cached is not None:
            return cached

    # Load from disk
    index_path = _get_knowledge_index(project_path)
    if not index_path.exists():
        return []

    with open(index_path) as f:
        data = yaml.safe_load(f) or {}

    items = []
    for item_data in data.get("items", []):
        triggers_data = item_data.get("triggers", {})
        scope_data = item_data.get("scope", {})
        meta_data = item_data.get("metadata", {})

        items.append(
            KnowledgeItem(
                id=item_data["id"],
                file=item_data["file"],
                triggers=KnowledgeTriggers(
                    keywords=tuple(triggers_data.get("keywords", [])),
                    patterns=tuple(triggers_data.get("patterns", [])),
                ),
                scope=KnowledgeScope(
                    skills=tuple(scope_data.get("skills", [])),
                    always=scope_data.get("always", False),
                ),
                metadata=KnowledgeMetadata(
                    added=meta_data.get("added", ""),
                    source=meta_data.get("source", ""),
                    tokens=meta_data.get("tokens", 0),
                    status=meta_data.get("status", ""),
                ),
                item_type=item_data.get("type", "knowledge"),
            )
        )

    # Update cache
    _set_cached_index(items)

    return items


def save_index(items: list[KnowledgeItem], project_path: Path | None = None) -> None:
    """Save knowledge index to YAML.

    Uses atomic write (temp file + rename) for crash safety.
    Invalidates the index cache after successful write.

    Args:
        items: List of KnowledgeItem objects to save
        project_path: Optional project path for project-scoped knowledge
    """
    from sage.atomic import atomic_write_yaml

    knowledge_dir = _get_knowledge_dir(project_path)
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "version": 1,
        "items": [
            {
                "id": item.id,
                "type": item.item_type,
                "file": item.file,
                "triggers": {
                    "keywords": list(item.triggers.keywords),
                    "patterns": list(item.triggers.patterns),
                },
                "scope": {
                    "skills": list(item.scope.skills),
                    "always": item.scope.always,
                },
                "metadata": {
                    "added": item.metadata.added,
                    "source": item.metadata.source,
                    "tokens": item.metadata.tokens,
                    "status": item.metadata.status,
                },
            }
            for item in items
        ],
    }

    # Atomic write via shared utility
    index_path = _get_knowledge_index(project_path)
    result = atomic_write_yaml(index_path, data, mode=0o600, sort_keys=False)
    if result.is_err():
        raise OSError(f"Failed to save knowledge index: {result.unwrap_err().message}")

    # Invalidate cache after successful write
    _invalidate_index_cache()


def _is_safe_path(base: Path, target: Path) -> bool:
    """Check if target path is safely within base directory."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return content
    # Find end of frontmatter
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return content
    return content[end_idx + 3 :].strip()


def load_knowledge_content(
    item: KnowledgeItem, project_path: Path | None = None
) -> KnowledgeItem:
    """Load the actual content for a knowledge item.

    Args:
        item: The KnowledgeItem to load content for
        project_path: Optional project path for project-scoped knowledge
    """
    knowledge_dir = _get_knowledge_dir(project_path)
    file_path = knowledge_dir / item.file

    # Security: ensure path doesn't escape knowledge directory
    if not _is_safe_path(knowledge_dir, file_path):
        return item

    if not file_path.exists():
        return item

    raw_content = file_path.read_text()
    # Strip frontmatter for display/injection
    content = _strip_frontmatter(raw_content)

    # Return new item with content loaded (immutable dataclass)
    return KnowledgeItem(
        id=item.id,
        file=item.file,
        triggers=item.triggers,
        scope=item.scope,
        metadata=KnowledgeMetadata(
            added=item.metadata.added,
            source=item.metadata.source,
            tokens=len(content) // 4,  # update token estimate
            status=item.metadata.status,
        ),
        item_type=item.item_type,
        content=content,
    )


def score_item_keyword(item: KnowledgeItem, query: str, skill_name: str) -> int:
    """
    Score a knowledge item using keyword/pattern matching only.

    Returns score >= 0. Higher = more relevant.
    """
    # Check skill scope
    if item.scope.skills and skill_name not in item.scope.skills:
        return 0

    # Always-inject items get base score
    if item.scope.always:
        return 10

    score = 0
    query_lower = query.lower()

    # Keyword matching
    for keyword in item.triggers.keywords:
        keyword_lower = keyword.lower()
        if keyword_lower in query_lower:
            # Exact word match scores higher
            if re.search(rf"\b{re.escape(keyword_lower)}\b", query_lower):
                score += 3
            else:
                score += 1

    # Pattern matching (regex)
    for pattern in item.triggers.patterns:
        try:
            if re.search(pattern, query, re.IGNORECASE):
                score += 2
        except re.error:
            pass  # Invalid regex, skip

    return score


# Backward compatibility alias
score_item = score_item_keyword


def score_item_combined(
    item: KnowledgeItem,
    query: str,
    skill_name: str,
    embedding_similarity: float | None = None,
) -> float:
    """
    Score a knowledge item using combined embedding and keyword scoring.

    When embeddings are available, uses a weighted combination from SageConfig:
    - embedding_weight (default 70%) for semantic similarity
    - keyword_weight (default 30%) for lexical matching

    Falls back to keyword-only scoring when embeddings unavailable.

    Args:
        item: The knowledge item to score
        query: The user query
        skill_name: Current skill name for scope filtering
        embedding_similarity: Pre-computed embedding similarity (0-1), or None

    Returns:
        Combined score (0-10 scale for comparability with keyword scoring)
    """
    # Check skill scope first
    if item.scope.skills and skill_name not in item.scope.skills:
        return 0.0

    # Always-inject items get max score
    if item.scope.always:
        return 10.0

    # Get keyword score (raw score, typically 0-9 range)
    keyword_score = score_item_keyword(item, query, skill_name)

    # If no embedding available, use keyword score only
    if embedding_similarity is None:
        return float(keyword_score)

    # Get weights from config
    config = get_sage_config()

    # Normalize keyword score to 0-1 range
    keyword_normalized = min(keyword_score / MAX_KEYWORD_SCORE, 1.0)

    # Combined weighted score
    combined = (
        config.embedding_weight * embedding_similarity + config.keyword_weight * keyword_normalized
    )

    # Scale back to 0-10 for threshold compatibility
    return combined * 10.0


def get_type_threshold(item_type: str) -> float:
    """Get the recall threshold for a knowledge type (0-10 scale).

    Args:
        item_type: The knowledge type

    Returns:
        Threshold on 0-10 scale
    """
    threshold_01 = TYPE_THRESHOLDS.get(item_type, DEFAULT_TYPE_THRESHOLD)
    return threshold_01 * 10.0


def recall_knowledge(
    query: str,
    skill_name: str,
    threshold: float | None = None,
    max_items: int = 3,
    max_tokens: int = 2000,
    use_embeddings: bool = True,
    item_types: tuple[str, ...] | None = None,
    project_path: Path | None = None,
) -> RecallResult:
    """
    Recall relevant knowledge items for a query.

    When embeddings are available and use_embeddings=True, uses combined
    semantic + keyword scoring. Falls back to keyword-only scoring otherwise.

    Uses type-aware thresholds when no explicit threshold is provided:
    - knowledge: 0.70 (standard)
    - preference: 0.30 (aggressive)
    - todo: 0.40 (moderate)
    - reference: 0.80 (conservative)

    Args:
        query: The user's query
        skill_name: Current skill being used
        threshold: Minimum score to include item (0-10 scale). If None, uses
                   type-specific thresholds.
        max_items: Maximum number of items to recall
        max_tokens: Maximum total tokens to recall
        use_embeddings: Whether to use embedding similarity (if available)
        item_types: Optional tuple of types to filter (None = all types)
        project_path: Optional project path for project-scoped knowledge

    Returns:
        RecallResult with matching items and total tokens
    """
    items = load_index(project_path=project_path)

    if not items:
        return RecallResult(items=[], total_tokens=0)

    # Filter out archived items (they're preserved but hidden from recall)
    items = [item for item in items if item.metadata.status != "archived"]

    # Filter by type if specified
    if item_types is not None:
        items = [item for item in items if item.item_type in item_types]

    if not items:
        return RecallResult(items=[], total_tokens=0)

    # Get embedding similarities if available
    embedding_similarities: dict[str, float] = {}
    if use_embeddings:
        embedding_similarities = _get_all_embedding_similarities(query)
        if embedding_similarities:
            logger.debug(f"Using embedding similarities for {len(embedding_similarities)} items")

    # Score all items with combined scoring
    scored: list[tuple[KnowledgeItem, float]] = []
    for item in items:
        similarity = embedding_similarities.get(item.id)
        score = score_item_combined(item, query, skill_name, similarity)
        scored.append((item, score))

    # Filter by score using type-aware thresholds (or explicit threshold)
    relevant: list[tuple[KnowledgeItem, float]] = []
    for item, score in scored:
        if threshold is not None:
            # Explicit threshold provided
            item_threshold = threshold
        else:
            # Use type-specific threshold
            item_threshold = get_type_threshold(item.item_type)

        if score >= item_threshold:
            relevant.append((item, score))

    relevant.sort(key=lambda x: x[1], reverse=True)

    # Select items within limits
    selected = []
    total_tokens = 0

    for item, score in relevant[:max_items]:
        loaded = load_knowledge_content(item)

        if total_tokens + loaded.metadata.tokens > max_tokens:
            continue  # Skip if would exceed token limit

        selected.append(loaded)
        total_tokens += loaded.metadata.tokens

    return RecallResult(items=selected, total_tokens=total_tokens)


def _sanitize_id(raw_id: str) -> str:
    """Sanitize an ID to prevent path traversal attacks."""
    # Only allow alphanumeric, hyphens, underscores
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_id).strip("-")
    # Ensure not empty
    return sanitized or "unnamed"


# Maximum regex pattern length to prevent ReDoS
MAX_PATTERN_LENGTH = 200

# Patterns that indicate potential ReDoS vulnerability
# These match common catastrophic backtracking patterns
DANGEROUS_REGEX_PATTERNS = [
    r"\([^)]*[+*]\)[+*]",  # (x+)+ or (x*)* - nested quantifiers
    r"\(\[[^\]]+\][+*]\)[+*]",  # ([a-z]+)+ style nested quantifiers
]


def _validate_regex_pattern(pattern: str) -> str | None:
    """Validate a regex pattern for safety.

    Returns None if valid, or an error message if invalid/dangerous.
    """
    # Length check
    if len(pattern) > MAX_PATTERN_LENGTH:
        return f"Pattern too long ({len(pattern)} > {MAX_PATTERN_LENGTH})"

    # Compilation check
    try:
        re.compile(pattern)
    except re.error as e:
        return f"Invalid regex: {e}"

    # Check for dangerous patterns (potential ReDoS)
    pattern_lower = pattern.lower()
    for dangerous in DANGEROUS_REGEX_PATTERNS:
        if re.search(dangerous, pattern_lower):
            return "Pattern contains potentially dangerous nested quantifiers"

    return None


def _validate_patterns(patterns: list[str]) -> list[str]:
    """Validate and filter regex patterns, logging warnings for invalid ones."""
    valid = []
    for p in patterns:
        error = _validate_regex_pattern(p)
        if error:
            logger.warning(f"Skipping invalid pattern '{p}': {error}")
        else:
            valid.append(p)
    return valid


def add_knowledge(
    content: str,
    knowledge_id: str,
    keywords: list[str],
    skill: str | None = None,
    source: str = "",
    patterns: list[str] | None = None,
    item_type: str = "knowledge",
    project_path: Path | None = None,
) -> KnowledgeItem:
    """
    Add a new knowledge item.

    Args:
        content: The knowledge content (markdown)
        knowledge_id: Unique identifier for this item
        keywords: Trigger keywords
        skill: Optional skill scope (None = global)
        source: Where this knowledge came from
        patterns: Optional regex patterns for matching
        item_type: Type of knowledge item (knowledge, preference, todo, reference)
        project_path: Optional project path for project-scoped knowledge

    Returns:
        The created KnowledgeItem
    """
    # Validate item type
    if item_type not in KNOWLEDGE_TYPES:
        logger.warning(f"Unknown knowledge type '{item_type}', using 'knowledge'")
        item_type = "knowledge"

    knowledge_dir = ensure_knowledge_dir(project_path)

    # Sanitize IDs to prevent path traversal
    safe_id = _sanitize_id(knowledge_id)
    safe_skill = _sanitize_id(skill) if skill else None

    # Determine file path
    if safe_skill:
        file_dir = knowledge_dir / "skills" / safe_skill
        file_dir.mkdir(parents=True, exist_ok=True)
        file_path = f"skills/{safe_skill}/{safe_id}.md"
    else:
        file_path = f"global/{safe_id}.md"

    # Build markdown content with frontmatter (Obsidian-compatible)
    added_date = datetime.now().strftime("%Y-%m-%d")
    frontmatter = {
        "id": safe_id,
        "type": item_type,
        "keywords": keywords,
        "source": source or None,
        "added": added_date,
    }
    if safe_skill:
        frontmatter["skill"] = safe_skill
    # Add status for todo items
    status = "pending" if item_type == "todo" else ""
    if status:
        frontmatter["status"] = status
    # Remove None values for cleaner YAML
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None}

    fm_yaml = yaml.safe_dump(
        frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True
    )
    md_content = f"---\n{fm_yaml}---\n\n{content}"

    # Write content file
    full_path = knowledge_dir / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(md_content)
    # Restrict permissions - knowledge content may be sensitive
    full_path.chmod(0o600)

    # Validate patterns to prevent ReDoS
    safe_patterns = _validate_patterns(patterns or [])

    # Create item (use safe_id for storage, original for display)
    item = KnowledgeItem(
        id=safe_id,
        file=file_path,
        triggers=KnowledgeTriggers(
            keywords=tuple(keywords),
            patterns=tuple(safe_patterns),
        ),
        scope=KnowledgeScope(
            skills=(safe_skill,) if safe_skill else (),
            always=False,
        ),
        metadata=KnowledgeMetadata(
            added=added_date,
            source=source,
            tokens=len(content) // 4,
            status=status,
        ),
        item_type=item_type,
        content=content,
    )

    # Update index
    items = load_index(project_path=project_path)
    # Remove existing item with same ID
    items = [i for i in items if i.id != safe_id]
    items.append(item)
    save_index(items, project_path=project_path)

    # Generate and store embedding (non-blocking, failures logged)
    _add_embedding(safe_id, content)

    # Run maintenance if enabled (non-blocking, failures logged)
    config = get_sage_config()
    if config.maintenance_on_save:
        try:
            run_knowledge_maintenance(project_path=project_path)
        except Exception as e:
            logger.warning(f"Knowledge maintenance failed: {e}")

    return item


def update_knowledge(
    knowledge_id: str,
    content: str | None = None,
    keywords: list[str] | None = None,
    status: str | None = None,
    source: str | None = None,
    project_path: Path | None = None,
) -> KnowledgeItem | None:
    """
    Update an existing knowledge item.

    Only provided fields are updated; others remain unchanged.
    Re-embeds automatically if content changes.

    Args:
        knowledge_id: ID of item to update
        content: New content (if changing)
        keywords: New keywords (if changing)
        status: New status - 'active', 'deprecated', or 'archived' (if changing)
        source: New source attribution (if changing)
        project_path: Optional project path for project-scoped knowledge

    Returns:
        Updated KnowledgeItem, or None if not found
    """
    knowledge_dir = _get_knowledge_dir(project_path)
    items = load_index(project_path=project_path)

    # Find existing item
    existing = None
    existing_idx = -1
    for idx, item in enumerate(items):
        if item.id == knowledge_id:
            existing = item
            existing_idx = idx
            break

    if existing is None:
        return None

    # Load current content if needed
    loaded = load_knowledge_content(existing)

    # Determine new values
    new_content = content if content is not None else loaded.content
    new_keywords = tuple(keywords) if keywords is not None else existing.triggers.keywords
    new_source = source if source is not None else existing.metadata.source
    new_status = status if status is not None else existing.metadata.status

    # Build updated item
    updated = KnowledgeItem(
        id=existing.id,
        file=existing.file,
        triggers=KnowledgeTriggers(
            keywords=new_keywords,
            patterns=existing.triggers.patterns,
        ),
        scope=existing.scope,
        metadata=KnowledgeMetadata(
            added=existing.metadata.added,
            source=new_source,
            tokens=len(new_content) // 4,  # rough token estimate
            status=new_status,
        ),
        item_type=existing.item_type,
        content=new_content,
    )

    # Update markdown file with new content/frontmatter
    frontmatter = {
        "id": updated.id,
        "type": updated.item_type,
        "keywords": list(updated.triggers.keywords),
        "source": updated.metadata.source or None,
        "added": updated.metadata.added,
    }
    if updated.scope.skills:
        if len(updated.scope.skills) == 1:
            frontmatter["skill"] = updated.scope.skills[0]
        else:
            frontmatter["skill"] = list(updated.scope.skills)
    if updated.metadata.status:
        frontmatter["status"] = updated.metadata.status
    # Remove None values
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None}

    fm_yaml = yaml.safe_dump(
        frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True
    )
    md_content = f"---\n{fm_yaml}---\n\n{new_content}"

    # Write updated file
    file_path = knowledge_dir / updated.file
    if _is_safe_path(knowledge_dir, file_path):
        file_path.write_text(md_content)
        file_path.chmod(0o600)

    # Update index
    items[existing_idx] = updated
    save_index(items, project_path=project_path)

    # Re-embed if content changed
    if content is not None and content != loaded.content:
        _add_embedding(updated.id, new_content)

    return updated


def deprecate_knowledge(
    knowledge_id: str,
    reason: str,
    replacement_id: str | None = None,
    project_path: Path | None = None,
) -> KnowledgeItem | None:
    """
    Mark a knowledge item as deprecated.

    Deprecated items still appear in search but show a warning.
    Use for outdated information that shouldn't be removed yet.

    Args:
        knowledge_id: ID of item to deprecate
        reason: Why this is deprecated
        replacement_id: Optional ID of replacement item
        project_path: Optional project path for project-scoped knowledge

    Returns:
        Updated KnowledgeItem, or None if not found
    """
    # Build deprecation note
    note = f"DEPRECATED: {reason}"
    if replacement_id:
        note += f" → See: {replacement_id}"

    return update_knowledge(
        knowledge_id=knowledge_id,
        status="deprecated",
        source=note,  # Store deprecation info in source field
        project_path=project_path,
    )


def archive_knowledge(
    knowledge_id: str, project_path: Path | None = None
) -> KnowledgeItem | None:
    """
    Archive a knowledge item (hidden from recall).

    Archived items are preserved but not included in retrieval.
    Use for obsolete items you want to keep for reference.

    Args:
        knowledge_id: ID of item to archive
        project_path: Optional project path for project-scoped knowledge

    Returns:
        Updated KnowledgeItem, or None if not found
    """
    return update_knowledge(
        knowledge_id=knowledge_id, status="archived", project_path=project_path
    )


def remove_knowledge(knowledge_id: str, project_path: Path | None = None) -> bool:
    """
    Remove a knowledge item.

    Args:
        knowledge_id: ID of item to remove
        project_path: Optional project path for project-scoped knowledge

    Returns:
        True if item was found and removed
    """
    knowledge_dir = _get_knowledge_dir(project_path)
    items = load_index(project_path=project_path)

    # Find and remove item
    removed_item = None
    for item in items:
        if item.id == knowledge_id:
            removed_item = item
            break

    if not removed_item:
        return False

    items = [i for i in items if i.id != knowledge_id]
    save_index(items, project_path=project_path)

    # Also remove content file (with path safety check)
    file_path = knowledge_dir / removed_item.file
    if _is_safe_path(knowledge_dir, file_path) and file_path.exists():
        file_path.unlink()

    # Remove embedding (non-blocking, failures logged)
    _remove_embedding(knowledge_id)

    return True


def list_knowledge(
    skill: str | None = None, project_path: Path | None = None
) -> list[KnowledgeItem]:
    """
    List knowledge items, optionally filtered by skill.

    Args:
        skill: Optional skill filter
        project_path: Optional project path for project-scoped knowledge
    """
    items = load_index(project_path=project_path)

    if skill is None:
        return items

    # Filter to items that apply to this skill
    return [item for item in items if not item.scope.skills or skill in item.scope.skills]


def format_recalled_context(result: RecallResult) -> str:
    """
    Format recalled knowledge for injection into context.
    """
    if not result.items:
        return ""

    parts = [
        f"\n---\n📚 Recalled Knowledge ({result.count} items, ~{result.total_tokens} tokens):\n"
    ]

    for item in result.items:
        parts.append(f"\n## {item.id}\n")
        if item.metadata.source:
            parts.append(f"*Source: {item.metadata.source}*\n\n")
        parts.append(item.content)
        parts.append("\n")

    parts.append("\n---\n")

    return "".join(parts)


# ============================================================================
# Todo Functions
# ============================================================================


def list_todos(
    status: str | None = None, project_path: Path | None = None
) -> list[KnowledgeItem]:
    """
    List todo items, optionally filtered by status.

    Args:
        status: Filter by status (pending, done) or None for all
        project_path: Optional project path for project-scoped knowledge

    Returns:
        List of todo KnowledgeItems
    """
    items = load_index(project_path=project_path)
    todos = [item for item in items if item.item_type == "todo"]

    if status is not None:
        todos = [item for item in todos if item.metadata.status == status]

    return todos


def mark_todo_done(todo_id: str, project_path: Path | None = None) -> bool:
    """
    Mark a todo item as done.

    Args:
        todo_id: The todo item ID
        project_path: Optional project path for project-scoped knowledge

    Returns:
        True if todo was found and marked done
    """
    items = load_index(project_path=project_path)

    # Find the todo
    todo_idx = None
    for i, item in enumerate(items):
        if item.id == todo_id and item.item_type == "todo":
            todo_idx = i
            break

    if todo_idx is None:
        return False

    # Create updated item with done status
    old_item = items[todo_idx]
    new_item = KnowledgeItem(
        id=old_item.id,
        file=old_item.file,
        triggers=old_item.triggers,
        scope=old_item.scope,
        metadata=KnowledgeMetadata(
            added=old_item.metadata.added,
            source=old_item.metadata.source,
            tokens=old_item.metadata.tokens,
            status="done",
        ),
        item_type=old_item.item_type,
        content=old_item.content,
    )

    items[todo_idx] = new_item
    save_index(items, project_path=project_path)

    # Also update the frontmatter in the file
    knowledge_dir = _get_knowledge_dir(project_path)
    file_path = knowledge_dir / old_item.file
    if _is_safe_path(knowledge_dir, file_path) and file_path.exists():
        content = file_path.read_text()
        # Update status in frontmatter
        content = re.sub(r"^status:\s*\w+", "status: done", content, flags=re.MULTILINE)
        file_path.write_text(content)
        file_path.chmod(0o600)

    return True


def get_pending_todos(project_path: Path | None = None) -> list[KnowledgeItem]:
    """Get all pending todo items for session-start injection.

    Args:
        project_path: Optional project path for project-scoped knowledge
    """
    return list_todos(status="pending", project_path=project_path)
