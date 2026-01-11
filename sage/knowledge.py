"""Knowledge recall system for Sage.

Automatically injects relevant knowledge snippets into context based on query matching.
Knowledge items are stored in ~/.sage/knowledge/ with keyword triggers.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from sage.config import SAGE_DIR


KNOWLEDGE_DIR = SAGE_DIR / "knowledge"
KNOWLEDGE_INDEX = KNOWLEDGE_DIR / "index.yaml"


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


@dataclass(frozen=True)
class KnowledgeItem:
    """A single knowledge item."""

    id: str
    file: str  # relative path from KNOWLEDGE_DIR
    triggers: KnowledgeTriggers
    scope: KnowledgeScope
    metadata: KnowledgeMetadata
    content: str = ""  # loaded on demand


@dataclass
class RecallResult:
    """Result of knowledge recall."""

    items: list[KnowledgeItem]
    total_tokens: int
    
    @property
    def count(self) -> int:
        return len(self.items)


def ensure_knowledge_dir() -> None:
    """Ensure knowledge directory structure exists."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_DIR / "global").mkdir(exist_ok=True)
    (KNOWLEDGE_DIR / "skills").mkdir(exist_ok=True)


def load_index() -> list[KnowledgeItem]:
    """Load knowledge index from YAML."""
    if not KNOWLEDGE_INDEX.exists():
        return []
    
    with open(KNOWLEDGE_INDEX) as f:
        data = yaml.safe_load(f) or {}
    
    items = []
    for item_data in data.get("items", []):
        triggers_data = item_data.get("triggers", {})
        scope_data = item_data.get("scope", {})
        meta_data = item_data.get("metadata", {})
        
        items.append(KnowledgeItem(
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
            ),
        ))
    
    return items


def save_index(items: list[KnowledgeItem]) -> None:
    """Save knowledge index to YAML."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    
    data = {
        "version": 1,
        "items": [
            {
                "id": item.id,
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
                },
            }
            for item in items
        ],
    }
    
    with open(KNOWLEDGE_INDEX, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def _is_safe_path(base: Path, target: Path) -> bool:
    """Check if target path is safely within base directory."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def load_knowledge_content(item: KnowledgeItem) -> KnowledgeItem:
    """Load the actual content for a knowledge item."""
    file_path = KNOWLEDGE_DIR / item.file
    
    # Security: ensure path doesn't escape knowledge directory
    if not _is_safe_path(KNOWLEDGE_DIR, file_path):
        return item
    
    if not file_path.exists():
        return item
    
    content = file_path.read_text()
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
        ),
        content=content,
    )


def score_item(item: KnowledgeItem, query: str, skill_name: str) -> int:
    """
    Score a knowledge item for relevance to the query.
    
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


def recall_knowledge(
    query: str,
    skill_name: str,
    threshold: int = 2,
    max_items: int = 3,
    max_tokens: int = 2000,
) -> RecallResult:
    """
    Recall relevant knowledge items for a query.
    
    Args:
        query: The user's query
        skill_name: Current skill being used
        threshold: Minimum score to include item
        max_items: Maximum number of items to recall
        max_tokens: Maximum total tokens to recall
    
    Returns:
        RecallResult with matching items and total tokens
    """
    items = load_index()
    
    # Score all items
    scored = [(item, score_item(item, query, skill_name)) for item in items]
    
    # Filter and sort by score
    relevant = [(item, score) for item, score in scored if score >= threshold]
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


def add_knowledge(
    content: str,
    knowledge_id: str,
    keywords: list[str],
    skill: str | None = None,
    source: str = "",
    patterns: list[str] | None = None,
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
    
    Returns:
        The created KnowledgeItem
    """
    ensure_knowledge_dir()
    
    # Sanitize IDs to prevent path traversal
    safe_id = _sanitize_id(knowledge_id)
    safe_skill = _sanitize_id(skill) if skill else None
    
    # Determine file path
    if safe_skill:
        file_dir = KNOWLEDGE_DIR / "skills" / safe_skill
        file_dir.mkdir(parents=True, exist_ok=True)
        file_path = f"skills/{safe_skill}/{safe_id}.md"
    else:
        file_path = f"global/{safe_id}.md"
    
    # Write content file
    full_path = KNOWLEDGE_DIR / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    
    # Create item (use safe_id for storage, original for display)
    item = KnowledgeItem(
        id=safe_id,
        file=file_path,
        triggers=KnowledgeTriggers(
            keywords=tuple(keywords),
            patterns=tuple(patterns or []),
        ),
        scope=KnowledgeScope(
            skills=(safe_skill,) if safe_skill else (),
            always=False,
        ),
        metadata=KnowledgeMetadata(
            added=datetime.now().strftime("%Y-%m-%d"),
            source=source,
            tokens=len(content) // 4,
        ),
        content=content,
    )
    
    # Update index
    items = load_index()
    # Remove existing item with same ID
    items = [i for i in items if i.id != safe_id]
    items.append(item)
    save_index(items)
    
    return item


def remove_knowledge(knowledge_id: str) -> bool:
    """
    Remove a knowledge item.
    
    Returns True if item was found and removed.
    """
    items = load_index()
    original_count = len(items)
    
    # Find and remove item
    removed_item = None
    for item in items:
        if item.id == knowledge_id:
            removed_item = item
            break
    
    if not removed_item:
        return False
    
    items = [i for i in items if i.id != knowledge_id]
    save_index(items)
    
    # Also remove content file (with path safety check)
    file_path = KNOWLEDGE_DIR / removed_item.file
    if _is_safe_path(KNOWLEDGE_DIR, file_path) and file_path.exists():
        file_path.unlink()
    
    return True


def list_knowledge(skill: str | None = None) -> list[KnowledgeItem]:
    """
    List knowledge items, optionally filtered by skill.
    """
    items = load_index()
    
    if skill is None:
        return items
    
    # Filter to items that apply to this skill
    return [
        item for item in items
        if not item.scope.skills or skill in item.scope.skills
    ]


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
