"""Checkpoint system for Sage.

Saves and restores semantic research state across sessions.
Checkpoints are stored as Markdown files with YAML frontmatter in
~/.sage/checkpoints/ or .sage/checkpoints/.

Format: .md files with YAML frontmatter (PKM/Obsidian compatible).
Legacy: .yaml files are still readable for backward compatibility.

When embeddings are available, provides deduplication by comparing thesis
embeddings to avoid saving semantically similar checkpoints.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from sage.config import SAGE_DIR, get_sage_config
from sage.types import CheckpointId

logger = logging.getLogger(__name__)


# Global checkpoints
CHECKPOINTS_DIR = SAGE_DIR / "checkpoints"


@dataclass(frozen=True)
class Source:
    """A source referenced in research."""

    id: str
    type: str  # person, document, code, api, observation
    take: str  # Decision-relevant summary
    relation: str  # supports, contradicts, nuances


@dataclass(frozen=True)
class Tension:
    """A disagreement between sources."""

    between: tuple[str, str]
    nature: str
    resolution: str  # unresolved, resolved, moot


@dataclass(frozen=True)
class Contribution:
    """A unique discovery or synthesis."""

    type: str  # discovery, experiment, synthesis, internal_knowledge
    content: str


@dataclass(frozen=True)
class CodeRef:
    """Reference to code that informed the checkpoint.

    Links research conclusions to specific code locations.
    Can be hydrated from the code index on checkpoint load.
    """

    file: str
    lines: tuple[int, int] | None = None
    chunk_id: str | None = None  # Link to codesage index for retrieval
    snippet: str | None = None  # Cached snippet (survives re-index)
    relevance: str = "context"  # "supports" | "contradicts" | "context" | "stale"


@dataclass(frozen=True)
class Checkpoint:
    """A semantic checkpoint of research state."""

    id: CheckpointId
    ts: str
    trigger: str  # manual, synthesis, branch_point, constraint, transition

    core_question: str
    thesis: str
    confidence: float

    open_questions: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    tensions: list[Tension] = field(default_factory=list)
    unique_contributions: list[Contribution] = field(default_factory=list)

    # Context hydration (v1.1) - helps Claude reconstruct mental state on restore
    key_evidence: list[str] = field(default_factory=list)  # Concrete facts supporting thesis
    reasoning_trace: str = ""  # Narrative of thinking process

    # Action context
    action_goal: str = ""
    action_type: str = ""  # decision, implementation, learning, exploration

    # Metadata
    skill: str | None = None
    project: str | None = None
    parent_checkpoint: str | None = None  # For branching
    message_count: int = 0
    token_estimate: int = 0

    # Template support (v1.2)
    template: str = "default"  # Template name for rendering
    custom_fields: dict = field(default_factory=dict)  # Extra fields for non-default templates

    # Code context (v1.3) - automatic context capture from session
    code_refs: tuple[CodeRef, ...] = ()  # Explicit code references
    files_explored: frozenset[str] = field(default_factory=frozenset)  # Files read during session
    files_changed: frozenset[str] = field(default_factory=frozenset)  # Files edited/written

    # Git context (v1.4) - branch/commit state when checkpoint was saved
    git_context: dict | None = None  # GitContext.to_dict() - branch, commit, dirty, recent_commits
    diff_summary: dict | None = None  # DiffSummary.to_dict() - uncommitted changes at save time

    # Linking (v4.0) - connect related checkpoints and knowledge
    continues_from: str | None = None  # Parent checkpoint ID (research continuation)
    related_knowledge: tuple[str, ...] = ()  # Related knowledge item IDs


def generate_checkpoint_id(description: str) -> CheckpointId:
    """Generate a checkpoint ID from timestamp and description."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    # Slugify description
    slug = re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")[:40]
    return CheckpointId(f"{ts}_{slug}")


def get_checkpoints_dir(project_path: Path | None = None) -> Path:
    """Get the checkpoints directory, preferring project-local if available."""
    if project_path:
        local_dir = project_path / ".sage" / "checkpoints"
        if local_dir.exists() or (project_path / ".sage").exists():
            return local_dir
    return CHECKPOINTS_DIR


def ensure_checkpoints_dir(project_path: Path | None = None) -> Path:
    """Ensure checkpoints directory exists and return it."""
    checkpoints_dir = get_checkpoints_dir(project_path)
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    return checkpoints_dir


# ============================================================================
# Markdown Serialization (PKM/Obsidian compatible)
# ============================================================================


def _checkpoint_to_markdown(checkpoint: Checkpoint) -> str:
    """Convert a checkpoint to Markdown with YAML frontmatter."""
    # Frontmatter contains structured metadata
    frontmatter = {
        "id": checkpoint.id,
        "type": "checkpoint",
        "ts": checkpoint.ts,
        "trigger": checkpoint.trigger,
        "confidence": checkpoint.confidence,
        "skill": checkpoint.skill,
        "project": checkpoint.project,
        "parent_checkpoint": checkpoint.parent_checkpoint,
        "message_count": checkpoint.message_count,
        "token_estimate": checkpoint.token_estimate,
        "action_goal": checkpoint.action_goal or None,
        "action_type": checkpoint.action_type or None,
        "template": checkpoint.template if checkpoint.template != "default" else None,
        # Code context (v1.3) - stored in frontmatter for structured access
        "files_explored": sorted(checkpoint.files_explored) if checkpoint.files_explored else None,
        "files_changed": sorted(checkpoint.files_changed) if checkpoint.files_changed else None,
        # Git context (v1.4)
        "git_context": checkpoint.git_context,
        "diff_summary": checkpoint.diff_summary,
        # Linking (v4.0)
        "continues_from": checkpoint.continues_from,
        "related_knowledge": list(checkpoint.related_knowledge) if checkpoint.related_knowledge else None,
    }
    # Remove None values for cleaner YAML
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None}

    # Build markdown body
    lines = []

    # Core question as title
    lines.append(f"# {checkpoint.core_question}")
    lines.append("")

    # Thesis
    lines.append("## Thesis")
    lines.append(checkpoint.thesis)
    lines.append("")

    # Key evidence (v1.1 - context hydration)
    if checkpoint.key_evidence:
        lines.append("## Key Evidence")
        for evidence in checkpoint.key_evidence:
            lines.append(f"- {evidence}")
        lines.append("")

    # Reasoning trace (v1.1 - context hydration)
    if checkpoint.reasoning_trace:
        lines.append("## Reasoning Trace")
        lines.append(checkpoint.reasoning_trace)
        lines.append("")

    # Open questions
    if checkpoint.open_questions:
        lines.append("## Open Questions")
        for q in checkpoint.open_questions:
            lines.append(f"- {q}")
        lines.append("")

    # Sources
    if checkpoint.sources:
        lines.append("## Sources")
        for s in checkpoint.sources:
            lines.append(f"- **{s.id}** ({s.type}): {s.take} — _{s.relation}_")
        lines.append("")

    # Tensions
    if checkpoint.tensions:
        lines.append("## Tensions")
        for t in checkpoint.tensions:
            lines.append(
                f"- **{t.between[0]}** vs **{t.between[1]}**: {t.nature} — _{t.resolution}_"
            )
        lines.append("")

    # Unique contributions
    if checkpoint.unique_contributions:
        lines.append("## Unique Contributions")
        for c in checkpoint.unique_contributions:
            lines.append(f"- **{c.type}**: {c.content}")
        lines.append("")

    # Code references (v1.3)
    if checkpoint.code_refs:
        lines.append("## Code References")
        for ref in checkpoint.code_refs:
            line_info = f":{ref.lines[0]}-{ref.lines[1]}" if ref.lines else ""
            relevance_marker = {
                "supports": "[+]",
                "contradicts": "[-]",
                "context": "[~]",
                "stale": "[!]",
            }.get(ref.relevance, "[?]")
            lines.append(f"- {relevance_marker} `{ref.file}{line_info}`")
            if ref.snippet:
                # Indent snippet as code block
                lines.append("  ```")
                for snippet_line in ref.snippet.split("\n")[:5]:  # Limit to 5 lines
                    lines.append(f"  {snippet_line}")
                lines.append("  ```")
        lines.append("")

    body = "\n".join(lines)

    # Combine frontmatter and body
    fm_yaml = yaml.safe_dump(
        frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True
    )
    return f"---\n{fm_yaml}---\n\n{body}"


def _markdown_to_checkpoint(content: str) -> Checkpoint | None:
    """Parse a Markdown checkpoint file into a Checkpoint object."""
    try:
        # Split frontmatter and body
        if not content.startswith("---"):
            return None

        # Find end of frontmatter
        end_idx = content.find("---", 3)
        if end_idx == -1:
            return None

        fm_text = content[3:end_idx].strip()
        body = content[end_idx + 3 :].strip()

        # Parse frontmatter
        fm = yaml.safe_load(fm_text) or {}

        # Parse body sections
        core_question = ""
        thesis = ""
        key_evidence: list[str] = []
        reasoning_trace = ""
        open_questions: list[str] = []
        sources: list[Source] = []
        tensions: list[Tension] = []
        contributions: list[Contribution] = []

        current_section = None
        section_lines: list[str] = []

        for line in body.split("\n"):
            if line.startswith("# "):
                core_question = line[2:].strip()
            elif line.startswith("## "):
                # Save previous section
                if current_section == "thesis":
                    thesis = "\n".join(section_lines).strip()
                elif current_section == "key_evidence":
                    for sl in section_lines:
                        if sl.startswith("- "):
                            key_evidence.append(sl[2:].strip())
                elif current_section == "reasoning_trace":
                    reasoning_trace = "\n".join(section_lines).strip()
                elif current_section == "open_questions":
                    for sl in section_lines:
                        if sl.startswith("- "):
                            open_questions.append(sl[2:].strip())
                elif current_section == "sources":
                    for sl in section_lines:
                        src = _parse_source_line(sl)
                        if src:
                            sources.append(src)
                elif current_section == "tensions":
                    for sl in section_lines:
                        tens = _parse_tension_line(sl)
                        if tens:
                            tensions.append(tens)
                elif current_section == "unique_contributions":
                    for sl in section_lines:
                        contrib = _parse_contribution_line(sl)
                        if contrib:
                            contributions.append(contrib)

                # Start new section
                section_name = line[3:].strip().lower().replace(" ", "_")
                current_section = section_name
                section_lines = []
            elif line.strip():
                section_lines.append(line)

        # Save last section
        if current_section == "thesis":
            thesis = "\n".join(section_lines).strip()
        elif current_section == "key_evidence":
            for sl in section_lines:
                if sl.startswith("- "):
                    key_evidence.append(sl[2:].strip())
        elif current_section == "reasoning_trace":
            reasoning_trace = "\n".join(section_lines).strip()
        elif current_section == "open_questions":
            for sl in section_lines:
                if sl.startswith("- "):
                    open_questions.append(sl[2:].strip())
        elif current_section == "sources":
            for sl in section_lines:
                src = _parse_source_line(sl)
                if src:
                    sources.append(src)
        elif current_section == "tensions":
            for sl in section_lines:
                tens = _parse_tension_line(sl)
                if tens:
                    tensions.append(tens)
        elif current_section == "unique_contributions":
            for sl in section_lines:
                contrib = _parse_contribution_line(sl)
                if contrib:
                    contributions.append(contrib)

        # Parse code context from frontmatter (v1.3)
        files_explored_raw = fm.get("files_explored", [])
        files_changed_raw = fm.get("files_changed", [])
        files_explored = frozenset(files_explored_raw) if files_explored_raw else frozenset()
        files_changed = frozenset(files_changed_raw) if files_changed_raw else frozenset()

        # Linking (v4.0)
        related_knowledge_raw = fm.get("related_knowledge", [])
        related_knowledge = tuple(related_knowledge_raw) if related_knowledge_raw else ()

        # YAML auto-converts ISO timestamps to datetime, convert back to string
        ts_value = fm.get("ts", "")
        if hasattr(ts_value, "isoformat"):
            ts_value = ts_value.isoformat()

        return Checkpoint(
            id=fm.get("id", ""),
            ts=ts_value,
            trigger=fm.get("trigger", ""),
            core_question=core_question,
            thesis=thesis,
            confidence=fm.get("confidence", 0.0),
            open_questions=open_questions,
            sources=sources,
            tensions=tensions,
            unique_contributions=contributions,
            key_evidence=key_evidence,
            reasoning_trace=reasoning_trace,
            action_goal=fm.get("action_goal", ""),
            action_type=fm.get("action_type", ""),
            skill=fm.get("skill"),
            project=fm.get("project"),
            parent_checkpoint=fm.get("parent_checkpoint"),
            message_count=fm.get("message_count", 0),
            token_estimate=fm.get("token_estimate", 0),
            template=fm.get("template", "default"),
            # Code context (v1.3)
            files_explored=files_explored,
            files_changed=files_changed,
            # Git context (v1.4)
            git_context=fm.get("git_context"),
            diff_summary=fm.get("diff_summary"),
            # Linking (v4.0)
            continues_from=fm.get("continues_from"),
            related_knowledge=related_knowledge,
        )
    except (yaml.YAMLError, KeyError, ValueError):
        return None


def _parse_source_line(line: str) -> Source | None:
    """Parse a source line: - **id** (type): take — _relation_"""
    if not line.startswith("- **"):
        return None
    try:
        # Extract id
        id_end = line.find("**", 4)
        if id_end == -1:
            return None
        source_id = line[4:id_end]

        # Extract type (in parentheses)
        type_start = line.find("(", id_end)
        type_end = line.find(")", type_start)
        if type_start == -1 or type_end == -1:
            return None
        source_type = line[type_start + 1 : type_end]

        # Extract take and relation
        rest = line[type_end + 2 :].strip()  # Skip ):
        if " — _" in rest:
            take, relation = rest.rsplit(" — _", 1)
            relation = relation.rstrip("_")
        else:
            take = rest
            relation = ""

        return Source(id=source_id, type=source_type, take=take, relation=relation)
    except (IndexError, ValueError):
        return None


def _parse_tension_line(line: str) -> Tension | None:
    """Parse a tension line: - **src1** vs **src2**: nature — _resolution_"""
    if not line.startswith("- **"):
        return None
    try:
        # Extract first source
        src1_end = line.find("**", 4)
        if src1_end == -1:
            return None
        src1 = line[4:src1_end]

        # Find "vs **"
        vs_idx = line.find(" vs **", src1_end)
        if vs_idx == -1:
            return None

        # Extract second source
        src2_start = vs_idx + 6
        src2_end = line.find("**", src2_start)
        if src2_end == -1:
            return None
        src2 = line[src2_start:src2_end]

        # Extract nature and resolution
        rest = line[src2_end + 3 :].strip()  # Skip **:
        if " — _" in rest:
            nature, resolution = rest.rsplit(" — _", 1)
            resolution = resolution.rstrip("_")
        else:
            nature = rest
            resolution = ""

        return Tension(between=(src1, src2), nature=nature, resolution=resolution)
    except (IndexError, ValueError):
        return None


def _parse_contribution_line(line: str) -> Contribution | None:
    """Parse a contribution line: - **type**: content"""
    if not line.startswith("- **"):
        return None
    try:
        type_end = line.find("**", 4)
        if type_end == -1:
            return None
        contrib_type = line[4:type_end]
        content = line[type_end + 3 :].strip()  # Skip **:
        return Contribution(type=contrib_type, content=content)
    except (IndexError, ValueError):
        return None


# ============================================================================
# Embedding-based Deduplication
# ============================================================================


def _get_checkpoint_embedding_store():
    """Load the checkpoint embedding store."""
    from sage import embeddings

    path = embeddings.get_checkpoint_embeddings_path()
    result = embeddings.load_embeddings(path)
    if result.is_err():
        logger.warning(f"Failed to load checkpoint embeddings: {result.unwrap_err().message}")
        return embeddings.EmbeddingStore.empty()
    return result.unwrap()


def _save_checkpoint_embedding_store(store) -> bool:
    """Save the checkpoint embedding store."""
    from sage import embeddings

    path = embeddings.get_checkpoint_embeddings_path()
    embeddings.ensure_embeddings_dir()
    result = embeddings.save_embeddings(path, store)
    if result.is_err():
        logger.warning(f"Failed to save checkpoint embeddings: {result.unwrap_err().message}")
        return False
    return True


def _add_checkpoint_embedding(checkpoint_id: str, thesis: str) -> bool:
    """Generate and store embedding for a checkpoint thesis.

    Args:
        checkpoint_id: The checkpoint ID
        thesis: The thesis text to embed

    Returns:
        True if embedding was added successfully
    """
    from sage import embeddings

    if not embeddings.is_available():
        logger.debug("Embeddings not available, skipping")
        return False

    result = embeddings.get_embedding(thesis)
    if result.is_err():
        logger.warning(f"Failed to generate embedding: {result.unwrap_err().message}")
        return False

    embedding = result.unwrap()
    store = _get_checkpoint_embedding_store()
    store = store.add(checkpoint_id, embedding)
    return _save_checkpoint_embedding_store(store)


def _remove_checkpoint_embedding(checkpoint_id: str) -> bool:
    """Remove embedding for a checkpoint.

    Args:
        checkpoint_id: The checkpoint ID

    Returns:
        True if embedding was removed successfully
    """
    from sage import embeddings

    if not embeddings.is_available():
        return True  # Nothing to remove

    store = _get_checkpoint_embedding_store()
    store = store.remove(checkpoint_id)
    return _save_checkpoint_embedding_store(store)


@dataclass(frozen=True)
class DuplicateCheckResult:
    """Result of checking for duplicate checkpoints."""

    is_duplicate: bool
    similar_checkpoint_id: str | None = None
    similarity_score: float = 0.0


def is_duplicate_checkpoint(
    thesis: str,
    threshold: float | None = None,
    max_recent: int = 20,
    project_path: Path | None = None,
) -> DuplicateCheckResult:
    """Check if a thesis is semantically similar to recent checkpoints.

    Args:
        thesis: The thesis text to check
        threshold: Similarity threshold (0-1). If None, uses dedup_threshold
                   from SageConfig (default 0.9).
        max_recent: Maximum number of recent checkpoints to check
        project_path: Optional project path for project-local checkpoints

    Returns:
        DuplicateCheckResult with is_duplicate flag and details
    """
    from sage import embeddings

    # Get threshold from config if not specified
    if threshold is None:
        config = get_sage_config(project_path)
        threshold = config.dedup_threshold

    if not embeddings.is_available():
        logger.debug("Embeddings not available, skipping dedup check")
        return DuplicateCheckResult(is_duplicate=False)

    # Get thesis embedding
    result = embeddings.get_embedding(thesis)
    if result.is_err():
        logger.warning(f"Failed to generate thesis embedding: {result.unwrap_err().message}")
        return DuplicateCheckResult(is_duplicate=False)

    thesis_embedding = result.unwrap()

    # Get recent checkpoints
    recent = list_checkpoints(project_path=project_path, limit=max_recent)
    if not recent:
        return DuplicateCheckResult(is_duplicate=False)

    # Load embeddings store
    store = _get_checkpoint_embedding_store()
    if len(store) == 0:
        return DuplicateCheckResult(is_duplicate=False)

    # Check similarity against recent checkpoints
    for cp in recent:
        cp_embedding = store.get(cp.id)
        if cp_embedding is None:
            continue

        similarity = embeddings.cosine_similarity(thesis_embedding, cp_embedding)
        if similarity >= threshold:
            logger.info(f"Duplicate detected: similarity {similarity:.2f} with checkpoint {cp.id}")
            return DuplicateCheckResult(
                is_duplicate=True,
                similar_checkpoint_id=cp.id,
                similarity_score=float(similarity),
            )

    return DuplicateCheckResult(is_duplicate=False)


# ============================================================================
# Checkpoint Search
# ============================================================================


@dataclass(frozen=True)
class SearchResult:
    """A checkpoint search result with similarity score."""

    checkpoint: Checkpoint
    similarity: float


def search_checkpoints(
    query: str,
    limit: int = 5,
    project_path: Path | None = None,
) -> list[SearchResult]:
    """Search checkpoints by semantic similarity to a query.

    Args:
        query: Search query text
        limit: Maximum results to return
        project_path: Optional project path

    Returns:
        List of SearchResult objects sorted by similarity (highest first)
    """
    from sage import embeddings

    if not embeddings.is_available():
        return []

    # Get query embedding
    result = embeddings.get_query_embedding(query)
    if result.is_err():
        logger.warning(f"Failed to embed query: {result.unwrap_err().message}")
        return []

    query_embedding = result.unwrap()

    # Load checkpoints and their embeddings
    checkpoints = list_checkpoints(project_path=project_path, limit=50)
    if not checkpoints:
        return []

    store = _get_checkpoint_embedding_store()
    if len(store) == 0:
        return []

    # Score and rank
    scored: list[SearchResult] = []
    for cp in checkpoints:
        cp_embedding = store.get(cp.id)
        if cp_embedding is None:
            continue
        similarity = float(embeddings.cosine_similarity(query_embedding, cp_embedding))
        scored.append(SearchResult(checkpoint=cp, similarity=similarity))

    # Sort by similarity descending
    scored.sort(key=lambda x: x.similarity, reverse=True)

    return scored[:limit]


# ============================================================================
# Checkpoint Maintenance
# ============================================================================


@dataclass(frozen=True)
class MaintenanceResult:
    """Result of checkpoint maintenance operation."""

    pruned_by_age: int = 0
    pruned_by_cap: int = 0
    total_remaining: int = 0


def run_checkpoint_maintenance(
    project_path: Path | None = None,
    max_age_days: int | None = None,
    max_count: int | None = None,
) -> MaintenanceResult:
    """Prune old checkpoints and cap to max count.

    Executes in order:
    1. Prune checkpoints older than max_age_days
    2. Cap remaining checkpoints to max_count (keeping most recent)
    3. Clean up orphaned embeddings for deleted checkpoints

    Args:
        project_path: Optional project path for project-local checkpoints
        max_age_days: Override config checkpoint_max_age_days (0 = never prune)
        max_count: Override config checkpoint_max_count (0 = unlimited)

    Returns:
        MaintenanceResult with counts of pruned and remaining checkpoints
    """
    from datetime import timedelta

    config = get_sage_config(project_path)

    # Use provided values or fall back to config
    if max_age_days is None:
        max_age_days = config.checkpoint_max_age_days
    if max_count is None:
        max_count = config.checkpoint_max_count

    checkpoints_dir = get_checkpoints_dir(project_path)

    if not checkpoints_dir.exists():
        return MaintenanceResult()

    # Get all checkpoint files with mtime
    checkpoint_files = []
    for ext in [".md", ".yaml"]:
        for f in checkpoints_dir.glob(f"*{ext}"):
            try:
                mtime = f.stat().st_mtime
                checkpoint_files.append((f, mtime))
            except OSError:
                # File may have been deleted, skip
                continue

    if not checkpoint_files:
        return MaintenanceResult()

    # Sort by mtime descending (newest first)
    checkpoint_files.sort(key=lambda x: x[1], reverse=True)

    pruned_by_age = 0
    pruned_by_cap = 0

    # Phase 1: Prune by age
    if max_age_days > 0:
        from datetime import datetime

        cutoff = datetime.now().timestamp() - timedelta(days=max_age_days).total_seconds()

        remaining_files = []
        for file_path, mtime in checkpoint_files:
            if mtime < cutoff:
                # File is too old - delete it
                checkpoint_id = file_path.stem
                try:
                    file_path.unlink()
                    _remove_checkpoint_embedding(checkpoint_id)
                    pruned_by_age += 1
                    logger.info(f"Pruned old checkpoint: {checkpoint_id}")
                except OSError as e:
                    logger.warning(f"Failed to prune checkpoint {checkpoint_id}: {e}")
            else:
                remaining_files.append((file_path, mtime))

        checkpoint_files = remaining_files

    # Phase 2: Cap by count
    if max_count > 0 and len(checkpoint_files) > max_count:
        # Files are sorted newest-first, so we delete from the end
        to_delete = checkpoint_files[max_count:]

        for file_path, _ in to_delete:
            checkpoint_id = file_path.stem
            try:
                file_path.unlink()
                _remove_checkpoint_embedding(checkpoint_id)
                pruned_by_cap += 1
                logger.info(f"Pruned excess checkpoint: {checkpoint_id}")
            except OSError as e:
                logger.warning(f"Failed to prune checkpoint {checkpoint_id}: {e}")

        checkpoint_files = checkpoint_files[:max_count]

    total_remaining = len(checkpoint_files)

    if pruned_by_age > 0 or pruned_by_cap > 0:
        logger.info(
            f"Checkpoint maintenance: pruned {pruned_by_age} by age, "
            f"{pruned_by_cap} by cap, {total_remaining} remaining"
        )

    return MaintenanceResult(
        pruned_by_age=pruned_by_age,
        pruned_by_cap=pruned_by_cap,
        total_remaining=total_remaining,
    )


def save_checkpoint(checkpoint: Checkpoint, project_path: Path | None = None) -> Path:
    """Save a checkpoint to disk as Markdown with YAML frontmatter.

    Uses atomic write (temp file + rename) to prevent data corruption on crash.
    Optionally runs maintenance to prune old checkpoints (if maintenance_on_save=True).
    Optionally commits to git if git_versioning_enabled (v4.0).
    """
    from sage.atomic import atomic_write_text

    checkpoints_dir = ensure_checkpoints_dir(project_path)

    # Convert to markdown format
    content = _checkpoint_to_markdown(checkpoint)

    file_path = checkpoints_dir / f"{checkpoint.id}.md"

    # Atomic write via shared utility
    result = atomic_write_text(file_path, content, mode=0o600)
    if result.is_err():
        raise OSError(f"Failed to save checkpoint: {result.unwrap_err().message}")

    # Store thesis embedding for deduplication (non-blocking, failures logged)
    if checkpoint.thesis:
        _add_checkpoint_embedding(checkpoint.id, checkpoint.thesis)

    # Run maintenance if enabled (non-blocking, failures logged)
    config = get_sage_config(project_path)
    if config.maintenance_on_save:
        try:
            run_checkpoint_maintenance(project_path)
        except Exception as e:
            logger.warning(f"Checkpoint maintenance failed: {e}")

    # Git versioning (v4.0) - commit if enabled
    if getattr(config, "git_versioning_enabled", False):
        try:
            from sage.git import commit_sage_change

            commit_sage_change(file_path, "checkpoint", checkpoint.id, project_path)
        except Exception as e:
            logger.debug(f"Git versioning failed: {e}")

    return file_path


def load_checkpoint(checkpoint_id: str, project_path: Path | None = None) -> Checkpoint | None:
    """Load a checkpoint by ID. Supports both .md and legacy .yaml formats."""
    checkpoints_dir = get_checkpoints_dir(project_path)

    # Try .md first (new format), then .yaml (legacy)
    for ext in [".md", ".yaml"]:
        file_path = checkpoints_dir / f"{checkpoint_id}{ext}"
        if file_path.exists():
            return _load_checkpoint_file(file_path)

    # Try partial match for both formats
    matches = list(checkpoints_dir.glob(f"*{checkpoint_id}*.md"))
    matches.extend(checkpoints_dir.glob(f"*{checkpoint_id}*.yaml"))
    if len(matches) == 1:
        return _load_checkpoint_file(matches[0])
    elif len(matches) > 1:
        return None  # Ambiguous

    return None


def _validate_checkpoint_schema(data: dict) -> str | None:
    """Validate checkpoint data structure.

    Returns None if valid, or an error message if invalid.
    """
    if not isinstance(data, dict):
        return "Checkpoint data must be a dictionary"

    if "checkpoint" not in data:
        return "Missing 'checkpoint' key"

    cp = data["checkpoint"]
    if not isinstance(cp, dict):
        return "'checkpoint' must be a dictionary"

    # Required fields
    required = ["id", "ts", "trigger", "core_question", "thesis", "confidence"]
    for field_name in required:
        if field_name not in cp:
            return f"Missing required field: {field_name}"

    # Type validation for critical fields
    if not isinstance(cp.get("confidence"), (int, float)):
        return "'confidence' must be a number"

    if not isinstance(cp.get("thesis"), str):
        return "'thesis' must be a string"

    return None


def _load_checkpoint_file(file_path: Path) -> Checkpoint | None:
    """Load a checkpoint from a file path. Supports both .md and .yaml formats."""
    try:
        with open(file_path) as f:
            content = f.read()

        # Detect format by extension or content
        if file_path.suffix == ".md" or content.startswith("---"):
            return _markdown_to_checkpoint(content)

        # Legacy YAML format
        data = yaml.safe_load(content)

        # Validate schema before accessing
        validation_error = _validate_checkpoint_schema(data)
        if validation_error:
            logger.warning(f"Invalid checkpoint {file_path}: {validation_error}")
            return None

        cp = data["checkpoint"]
        meta = cp.get("metadata", {})
        action = cp.get("action", {})

        # YAML auto-converts ISO timestamps to datetime, convert back to string
        ts_value = cp["ts"]
        if hasattr(ts_value, "isoformat"):
            ts_value = ts_value.isoformat()

        return Checkpoint(
            id=cp["id"],
            ts=ts_value,
            trigger=cp["trigger"],
            core_question=cp["core_question"],
            thesis=cp["thesis"],
            confidence=cp["confidence"],
            open_questions=cp.get("open_questions", []),
            sources=[
                Source(
                    id=s["id"],
                    type=s["type"],
                    take=s["take"],
                    relation=s["relation"],
                )
                for s in cp.get("sources", [])
            ],
            tensions=[
                Tension(
                    between=tuple(t["between"]),
                    nature=t["nature"],
                    resolution=t["resolution"],
                )
                for t in cp.get("tensions", [])
            ],
            unique_contributions=[
                Contribution(type=c["type"], content=c["content"])
                for c in cp.get("unique_contributions", [])
            ],
            action_goal=action.get("goal", ""),
            action_type=action.get("type", ""),
            skill=meta.get("skill"),
            project=meta.get("project"),
            parent_checkpoint=meta.get("parent_checkpoint"),
            message_count=meta.get("message_count", 0),
            token_estimate=meta.get("token_estimate", 0),
        )
    except (KeyError, yaml.YAMLError):
        return None


def list_checkpoints(
    project_path: Path | None = None,
    skill: str | None = None,
    limit: int = 20,
) -> list[Checkpoint]:
    """List checkpoints, most recent first. Supports both .md and .yaml formats."""
    checkpoints_dir = get_checkpoints_dir(project_path)

    if not checkpoints_dir.exists():
        return []

    # Gather both .md and .yaml files
    files = list(checkpoints_dir.glob("*.md"))
    files.extend(checkpoints_dir.glob("*.yaml"))

    checkpoints = []
    for file_path in sorted(files, reverse=True):
        cp = _load_checkpoint_file(file_path)
        if cp:
            if skill and cp.skill != skill:
                continue
            checkpoints.append(cp)
            if len(checkpoints) >= limit:
                break

    return checkpoints


def delete_checkpoint(checkpoint_id: str, project_path: Path | None = None) -> bool:
    """Delete a checkpoint by ID. Supports both .md and .yaml formats."""
    checkpoints_dir = get_checkpoints_dir(project_path)
    actual_id = checkpoint_id
    file_path = None

    # Try exact match for both formats
    for ext in [".md", ".yaml"]:
        candidate = checkpoints_dir / f"{checkpoint_id}{ext}"
        if candidate.exists():
            file_path = candidate
            break

    if file_path is None:
        # Try partial match for both formats
        matches = list(checkpoints_dir.glob(f"*{checkpoint_id}*.md"))
        matches.extend(checkpoints_dir.glob(f"*{checkpoint_id}*.yaml"))
        if len(matches) == 1:
            file_path = matches[0]
            # Extract actual ID from filename
            actual_id = file_path.stem
        else:
            return False

    file_path.unlink()

    # Remove embedding (non-blocking, failures logged)
    _remove_checkpoint_embedding(actual_id)

    return True


def format_checkpoint_for_context(checkpoint: Checkpoint, use_toon: bool | None = None) -> str:
    """Format a checkpoint for injection into conversation context.

    Args:
        checkpoint: The checkpoint to format
        use_toon: If True, use TOON-style compact format. If None, check config.

    Returns:
        Formatted string for context injection
    """
    if use_toon is None:
        from sage.config import get_sage_config

        config = get_sage_config()
        use_toon = getattr(config, "output_format", "markdown") == "toon"

    if use_toon:
        return format_checkpoint_toon(checkpoint)

    parts = [
        "# Research Context (Restored from Checkpoint)\n",
        f"*Checkpoint: {checkpoint.id}*\n",
        f"*Saved: {checkpoint.ts[:16].replace('T', ' ')} | Confidence: {checkpoint.confidence:.0%}*\n\n",  # noqa: E501
        "## Core Question\n",
        f"{checkpoint.core_question}\n\n",
        "## Current Thesis\n",
        f"{checkpoint.thesis}\n\n",
    ]

    # Key evidence (v1.1 - context hydration)
    if checkpoint.key_evidence:
        parts.append("## Key Evidence\n")
        for evidence in checkpoint.key_evidence:
            parts.append(f"- {evidence}\n")
        parts.append("\n")

    # Reasoning trace (v1.1 - context hydration)
    if checkpoint.reasoning_trace:
        parts.append("## Reasoning Trace\n")
        parts.append(f"{checkpoint.reasoning_trace}\n\n")

    if checkpoint.open_questions:
        parts.append("## Open Questions\n")
        for q in checkpoint.open_questions:
            parts.append(f"- {q}\n")
        parts.append("\n")

    if checkpoint.sources:
        parts.append("## Key Sources\n")
        for s in checkpoint.sources:
            indicator = {"supports": "[+]", "contradicts": "[-]", "nuances": "[~]"}.get(
                s.relation, "[?]"
            )
            parts.append(f"- {indicator} **{s.id}** ({s.type}): {s.take}\n")
        parts.append("\n")

    if checkpoint.tensions:
        unresolved = [t for t in checkpoint.tensions if t.resolution == "unresolved"]
        if unresolved:
            parts.append("## Unresolved Tensions\n")
            for t in unresolved:
                parts.append(f"- **{t.between[0]}** vs **{t.between[1]}**: {t.nature}\n")
            parts.append("\n")

    if checkpoint.unique_contributions:
        parts.append("## Unique Discoveries\n")
        for c in checkpoint.unique_contributions:
            parts.append(f"- *{c.type}*: {c.content}\n")
        parts.append("\n")

    if checkpoint.action_goal:
        parts.append("## Action Context\n")
        parts.append(f"**Goal**: {checkpoint.action_goal}\n")
        parts.append(f"**Type**: {checkpoint.action_type}\n")
        parts.append("\n")

    # Code context (v1.3)
    if checkpoint.code_refs:
        parts.append("## Code References\n")
        for ref in checkpoint.code_refs:
            line_info = f":{ref.lines[0]}-{ref.lines[1]}" if ref.lines else ""
            relevance_marker = {
                "supports": "[+]",
                "contradicts": "[-]",
                "context": "[~]",
                "stale": "[!]",
            }.get(ref.relevance, "[?]")
            parts.append(f"- {relevance_marker} `{ref.file}{line_info}`\n")
        parts.append("\n")

    if checkpoint.files_changed:
        parts.append("## Files Changed\n")
        for f in sorted(checkpoint.files_changed):
            parts.append(f"- `{f}`\n")
        parts.append("\n")

    if checkpoint.files_explored and not checkpoint.files_changed:
        # Only show explored if no changes (otherwise it's redundant)
        parts.append("## Files Explored\n")
        for f in sorted(checkpoint.files_explored)[:10]:  # Limit to 10
            parts.append(f"- `{f}`\n")
        if len(checkpoint.files_explored) > 10:
            parts.append(f"- _...and {len(checkpoint.files_explored) - 10} more_\n")
        parts.append("\n")

    # Git context (v1.4)
    if checkpoint.git_context:
        gc = checkpoint.git_context
        parts.append("## Git Context\n")
        branch = gc.get("branch", "unknown")
        commit = gc.get("commit", "unknown")
        dirty = " (dirty)" if gc.get("dirty") else ""
        parts.append(f"Branch: `{branch}` @ `{commit}`{dirty}\n")
        if gc.get("recent_commits"):
            parts.append("Recent commits:\n")
            for c in gc.get("recent_commits", [])[:3]:
                parts.append(f"- {c}\n")
        parts.append("\n")

    # Diff summary (uncommitted changes at save time)
    if checkpoint.diff_summary:
        ds = checkpoint.diff_summary
        insertions = ds.get("insertions", 0)
        deletions = ds.get("deletions", 0)
        files_changed = ds.get("files_changed", [])
        staged_files = ds.get("staged_files", [])

        if files_changed or staged_files:
            parts.append("## Uncommitted Changes (at save time)\n")
            parts.append(f"+{insertions} -{deletions} lines\n")
            all_files = sorted(set(files_changed) | set(staged_files))
            for f in all_files[:5]:
                staged_marker = "●" if f in staged_files else "○"
                parts.append(f"- {staged_marker} `{f}`\n")
            if len(all_files) > 5:
                parts.append(f"- _...and {len(all_files) - 5} more files_\n")
            parts.append("\n")

    return "".join(parts)


def format_checkpoint_toon(checkpoint: Checkpoint) -> str:
    """Format a checkpoint using TOON-inspired compact format.

    Inspired by TOON (https://toon-format.org) by @mixeden.

    Uses TOON principles for token-efficient, parseable output:
    - Counts in headers: `## Sources [3]`
    - Tabular data with field hints: `sources[3]{id,type,take,rel}:`
    - Relation icons: [+] supports, [-] contradicts, [~] nuances

    This format is optimized for both LLM parsing and human scanning.
    """
    parts = [
        "# Research Context\n",
        f"checkpoint: {checkpoint.id}\n",
        f"saved: {checkpoint.ts[:16].replace('T', ' ')} | confidence: {checkpoint.confidence:.0%}\n\n",
    ]

    # Core question and thesis (prose - keep as-is)
    parts.append(f"## Question\n{checkpoint.core_question}\n\n")
    parts.append(f"## Thesis\n{checkpoint.thesis}\n\n")

    # Key evidence - simple list with count
    if checkpoint.key_evidence:
        parts.append(f"## Evidence [{len(checkpoint.key_evidence)}]\n")
        for e in checkpoint.key_evidence:
            parts.append(f"- {e}\n")
        parts.append("\n")

    # Reasoning trace (prose)
    if checkpoint.reasoning_trace:
        parts.append(f"## Reasoning\n{checkpoint.reasoning_trace}\n\n")

    # Open questions - simple list with count
    if checkpoint.open_questions:
        parts.append(f"## Open [{len(checkpoint.open_questions)}]\n")
        for q in checkpoint.open_questions:
            parts.append(f"- {q}\n")
        parts.append("\n")

    # Sources - TOON tabular format for 3+, list for fewer
    if checkpoint.sources:
        n = len(checkpoint.sources)
        if n >= 3:
            parts.append(f"## Sources [{n}]\n")
            parts.append(f"sources[{n}]{{id,type,take,rel}}:\n")
            for s in checkpoint.sources:
                rel = {"supports": "+", "contradicts": "-", "nuances": "~"}.get(s.relation, "?")
                # Escape commas in take
                take = s.take.replace(",", ";") if s.take else ""
                parts.append(f"  {s.id},{s.type},{take},{rel}\n")
        else:
            parts.append(f"## Sources [{n}]\n")
            for s in checkpoint.sources:
                icon = {"supports": "[+]", "contradicts": "[-]", "nuances": "[~]"}.get(
                    s.relation, "[?]"
                )
                parts.append(f"- {icon} **{s.id}** ({s.type}): {s.take}\n")
        parts.append("\n")

    # Tensions - TOON for 3+
    if checkpoint.tensions:
        unresolved = [t for t in checkpoint.tensions if t.resolution == "unresolved"]
        if unresolved:
            n = len(unresolved)
            if n >= 3:
                parts.append(f"## Tensions [{n}]\n")
                parts.append(f"tensions[{n}]{{a,b,nature}}:\n")
                for t in unresolved:
                    nature = t.nature.replace(",", ";") if t.nature else ""
                    parts.append(f"  {t.between[0]},{t.between[1]},{nature}\n")
            else:
                parts.append(f"## Tensions [{n}]\n")
                for t in unresolved:
                    parts.append(f"- **{t.between[0]}** vs **{t.between[1]}**: {t.nature}\n")
            parts.append("\n")

    # Unique contributions
    if checkpoint.unique_contributions:
        n = len(checkpoint.unique_contributions)
        parts.append(f"## Discoveries [{n}]\n")
        for c in checkpoint.unique_contributions:
            parts.append(f"- *{c.type}*: {c.content}\n")
        parts.append("\n")

    # Action context (compact)
    if checkpoint.action_goal:
        parts.append("## Action\n")
        parts.append(f"goal: {checkpoint.action_goal}\n")
        parts.append(f"type: {checkpoint.action_type}\n\n")

    # Code references - TOON tabular for 3+
    if checkpoint.code_refs:
        n = len(checkpoint.code_refs)
        if n >= 3:
            parts.append(f"## Code [{n}]\n")
            parts.append(f"refs[{n}]{{file,lines,rel}}:\n")
            for ref in checkpoint.code_refs:
                line_info = f"{ref.lines[0]}-{ref.lines[1]}" if ref.lines else "-"
                rel = {"supports": "+", "contradicts": "-", "context": "~", "stale": "!"}.get(
                    ref.relevance, "?"
                )
                parts.append(f"  {ref.file},{line_info},{rel}\n")
        else:
            parts.append(f"## Code [{n}]\n")
            for ref in checkpoint.code_refs:
                line_info = f":{ref.lines[0]}-{ref.lines[1]}" if ref.lines else ""
                icon = {"supports": "[+]", "contradicts": "[-]", "context": "[~]", "stale": "[!]"}.get(
                    ref.relevance, "[?]"
                )
                parts.append(f"- {icon} `{ref.file}{line_info}`\n")
        parts.append("\n")

    # Files changed - TOON list
    if checkpoint.files_changed:
        n = len(checkpoint.files_changed)
        parts.append(f"## Changed [{n}]\n")
        if n >= 5:
            parts.append(f"files[{n}]:\n")
            for f in sorted(checkpoint.files_changed):
                parts.append(f"  {f}\n")
        else:
            for f in sorted(checkpoint.files_changed):
                parts.append(f"- `{f}`\n")
        parts.append("\n")

    # Files explored (if no changes)
    if checkpoint.files_explored and not checkpoint.files_changed:
        n = len(checkpoint.files_explored)
        display_n = min(n, 10)
        parts.append(f"## Explored [{n}]\n")
        if n >= 5:
            parts.append(f"files[{display_n}]:\n")
            for f in sorted(checkpoint.files_explored)[:10]:
                parts.append(f"  {f}\n")
        else:
            for f in sorted(checkpoint.files_explored)[:10]:
                parts.append(f"- `{f}`\n")
        if n > 10:
            parts.append(f"  ...+{n - 10} more\n")
        parts.append("\n")

    # Git context (compact single line)
    if checkpoint.git_context:
        gc = checkpoint.git_context
        branch = gc.get("branch", "?")
        commit = gc.get("commit", "?")[:7]
        dirty = "*" if gc.get("dirty") else ""
        parts.append("## Git\n")
        parts.append(f"branch: {branch} @ {commit}{dirty}\n\n")

    return "".join(parts)


def create_checkpoint_from_dict(
    data: dict,
    trigger: str = "manual",
    template: str = "default",
) -> Checkpoint:
    """Create a Checkpoint from a dictionary (e.g., parsed from Claude's output).

    Args:
        data: Checkpoint data dictionary
        trigger: What triggered this checkpoint
        template: Template name for rendering (default: "default")

    Returns:
        Checkpoint object
    """
    ts = datetime.now(UTC).isoformat()

    # Generate ID
    description = data.get("thesis", data.get("decision", "checkpoint"))[:50]
    checkpoint_id = generate_checkpoint_id(description)

    # Extract custom fields (anything not in standard schema)
    standard_fields = {
        "core_question",
        "thesis",
        "confidence",
        "open_questions",
        "sources",
        "tensions",
        "unique_contributions",
        "key_evidence",
        "reasoning_trace",
        "action",
        "decision",
        "options_considered",
        "tradeoffs",
        "recommendation",
        "risks",
        "summary",
        "issues_found",
        "suggestions",
        "files_reviewed",
        # Code context (v1.3)
        "code_refs",
        "files_explored",
        "files_changed",
    }
    custom_fields = {k: v for k, v in data.items() if k not in standard_fields}

    return Checkpoint(
        id=checkpoint_id,
        ts=ts,
        trigger=trigger,
        core_question=data.get("core_question", ""),
        thesis=data.get("thesis", ""),
        confidence=float(data.get("confidence", 0.5)),
        open_questions=data.get("open_questions", []),
        sources=[
            Source(
                id=s.get("id", ""),
                type=s.get("type", ""),
                take=s.get("take", ""),
                relation=s.get("relation", ""),
            )
            for s in data.get("sources", [])
        ],
        tensions=[
            Tension(
                between=tuple(t.get("between", ["", ""])),
                nature=t.get("nature", ""),
                resolution=t.get("resolution", "unresolved"),
            )
            for t in data.get("tensions", [])
        ],
        unique_contributions=[
            Contribution(
                type=c.get("type", ""),
                content=c.get("content", ""),
            )
            for c in data.get("unique_contributions", [])
        ],
        key_evidence=data.get("key_evidence", []),
        reasoning_trace=data.get("reasoning_trace", ""),
        action_goal=data.get("action", {}).get("goal", ""),
        action_type=data.get("action", {}).get("type", ""),
        template=template,
        custom_fields=custom_fields,
        # Code context (v1.3)
        code_refs=tuple(
            CodeRef(
                file=r.get("file", ""),
                lines=tuple(r["lines"]) if r.get("lines") else None,
                chunk_id=r.get("chunk_id"),
                snippet=r.get("snippet"),
                relevance=r.get("relevance", "context"),
            )
            for r in data.get("code_refs", [])
        ),
        files_explored=frozenset(data.get("files_explored", [])),
        files_changed=frozenset(data.get("files_changed", [])),
    )


def enrich_checkpoint_with_code_context(
    checkpoint: Checkpoint,
    transcript_path: Path,
) -> Checkpoint:
    """Enrich a checkpoint with code context from the session transcript.

    Extracts file interactions from the transcript and adds them to the
    checkpoint's files_explored and files_changed fields.

    Args:
        checkpoint: The checkpoint to enrich
        transcript_path: Path to the JSONL transcript file

    Returns:
        New Checkpoint with code context added (immutable, so returns copy)
    """
    from sage.transcript import get_session_code_context

    context = get_session_code_context(transcript_path)

    if context.all_files:
        # Merge with any existing context (in case checkpoint already has some)
        new_files_explored = checkpoint.files_explored | context.files_read
        new_files_changed = checkpoint.files_changed | context.files_changed

        # Create new checkpoint with updated fields
        # Using dataclasses.replace would be cleaner but Checkpoint is frozen
        return Checkpoint(
            id=checkpoint.id,
            ts=checkpoint.ts,
            trigger=checkpoint.trigger,
            core_question=checkpoint.core_question,
            thesis=checkpoint.thesis,
            confidence=checkpoint.confidence,
            open_questions=checkpoint.open_questions,
            sources=checkpoint.sources,
            tensions=checkpoint.tensions,
            unique_contributions=checkpoint.unique_contributions,
            key_evidence=checkpoint.key_evidence,
            reasoning_trace=checkpoint.reasoning_trace,
            action_goal=checkpoint.action_goal,
            action_type=checkpoint.action_type,
            skill=checkpoint.skill,
            project=checkpoint.project,
            parent_checkpoint=checkpoint.parent_checkpoint,
            message_count=checkpoint.message_count,
            token_estimate=checkpoint.token_estimate,
            template=checkpoint.template,
            custom_fields=checkpoint.custom_fields,
            code_refs=checkpoint.code_refs,
            files_explored=new_files_explored,
            files_changed=new_files_changed,
            git_context=checkpoint.git_context,
            diff_summary=checkpoint.diff_summary,
        )

    return checkpoint


def enrich_checkpoint_with_git_context(
    checkpoint: Checkpoint,
    project_path: Path | None = None,
) -> Checkpoint:
    """Enrich a checkpoint with current git state.

    Captures branch, commit, dirty state, and uncommitted changes.

    Args:
        checkpoint: The checkpoint to enrich
        project_path: Repository path

    Returns:
        New Checkpoint with git context added (immutable, so returns copy)
    """
    from sage.git import capture_git_context, get_diff_summary

    git_ctx = capture_git_context(project_path)
    if git_ctx is None:
        return checkpoint  # Not a git repo

    diff = get_diff_summary(project_path)

    return Checkpoint(
        id=checkpoint.id,
        ts=checkpoint.ts,
        trigger=checkpoint.trigger,
        core_question=checkpoint.core_question,
        thesis=checkpoint.thesis,
        confidence=checkpoint.confidence,
        open_questions=checkpoint.open_questions,
        sources=checkpoint.sources,
        tensions=checkpoint.tensions,
        unique_contributions=checkpoint.unique_contributions,
        key_evidence=checkpoint.key_evidence,
        reasoning_trace=checkpoint.reasoning_trace,
        action_goal=checkpoint.action_goal,
        action_type=checkpoint.action_type,
        skill=checkpoint.skill,
        project=checkpoint.project,
        parent_checkpoint=checkpoint.parent_checkpoint,
        message_count=checkpoint.message_count,
        token_estimate=checkpoint.token_estimate,
        template=checkpoint.template,
        custom_fields=checkpoint.custom_fields,
        code_refs=checkpoint.code_refs,
        files_explored=checkpoint.files_explored,
        files_changed=checkpoint.files_changed,
        git_context=git_ctx.to_dict(),
        diff_summary=diff.to_dict() if diff.files_changed or diff.staged_files else None,
    )
