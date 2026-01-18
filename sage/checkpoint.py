"""Checkpoint system for Sage.

Saves and restores semantic research state across sessions.
Checkpoints are stored as Markdown files with YAML frontmatter in
~/.sage/checkpoints/ or .sage/checkpoints/.

Format: .md files with YAML frontmatter (PKM/Obsidian compatible).
Legacy: .yaml files are still readable for backward compatibility.

When embeddings are available, provides deduplication by comparing thesis
embeddings to avoid saving semantically similar checkpoints.
"""

import hashlib
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from sage.config import SAGE_DIR, get_sage_config

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


@dataclass
class Checkpoint:
    """A semantic checkpoint of research state."""

    id: str
    ts: str
    trigger: str  # manual, synthesis, branch_point, constraint, transition

    core_question: str
    thesis: str
    confidence: float

    open_questions: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    tensions: list[Tension] = field(default_factory=list)
    unique_contributions: list[Contribution] = field(default_factory=list)

    # Action context
    action_goal: str = ""
    action_type: str = ""  # decision, implementation, learning, exploration

    # Metadata
    skill: str | None = None
    project: str | None = None
    parent_checkpoint: str | None = None  # For branching
    message_count: int = 0
    token_estimate: int = 0


def generate_checkpoint_id(description: str) -> str:
    """Generate a checkpoint ID from timestamp and description."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    # Slugify description
    slug = re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")[:40]
    return f"{ts}_{slug}"


def generate_short_hash(content: str) -> str:
    """Generate a short hash for a checkpoint (Manus-style)."""
    return hashlib.sha256(content.encode()).hexdigest()[:8]


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
            lines.append(f"- **{t.between[0]}** vs **{t.between[1]}**: {t.nature} — _{t.resolution}_")
        lines.append("")

    # Unique contributions
    if checkpoint.unique_contributions:
        lines.append("## Unique Contributions")
        for c in checkpoint.unique_contributions:
            lines.append(f"- **{c.type}**: {c.content}")
        lines.append("")

    body = "\n".join(lines)

    # Combine frontmatter and body
    fm_yaml = yaml.safe_dump(frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True)
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
        body = content[end_idx + 3:].strip()

        # Parse frontmatter
        fm = yaml.safe_load(fm_text) or {}

        # Parse body sections
        core_question = ""
        thesis = ""
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

        return Checkpoint(
            id=fm.get("id", ""),
            ts=fm.get("ts", ""),
            trigger=fm.get("trigger", ""),
            core_question=core_question,
            thesis=thesis,
            confidence=fm.get("confidence", 0.0),
            open_questions=open_questions,
            sources=sources,
            tensions=tensions,
            unique_contributions=contributions,
            action_goal=fm.get("action_goal", ""),
            action_type=fm.get("action_type", ""),
            skill=fm.get("skill"),
            project=fm.get("project"),
            parent_checkpoint=fm.get("parent_checkpoint"),
            message_count=fm.get("message_count", 0),
            token_estimate=fm.get("token_estimate", 0),
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
        source_type = line[type_start + 1:type_end]

        # Extract take and relation
        rest = line[type_end + 2:].strip()  # Skip ):
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
        rest = line[src2_end + 3:].strip()  # Skip **:
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
        content = line[type_end + 3:].strip()  # Skip **:
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


def save_checkpoint(checkpoint: Checkpoint, project_path: Path | None = None) -> Path:
    """Save a checkpoint to disk as Markdown with YAML frontmatter."""
    checkpoints_dir = ensure_checkpoints_dir(project_path)

    # Convert to markdown format
    content = _checkpoint_to_markdown(checkpoint)

    file_path = checkpoints_dir / f"{checkpoint.id}.md"
    with open(file_path, "w") as f:
        f.write(content)
    # Restrict permissions - checkpoints may contain research context
    file_path.chmod(0o600)

    # Store thesis embedding for deduplication (non-blocking, failures logged)
    if checkpoint.thesis:
        _add_checkpoint_embedding(checkpoint.id, checkpoint.thesis)

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
    for field in required:
        if field not in cp:
            return f"Missing required field: {field}"

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

        return Checkpoint(
            id=cp["id"],
            ts=cp["ts"],
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


def format_checkpoint_for_context(checkpoint: Checkpoint) -> str:
    """Format a checkpoint for injection into conversation context."""
    parts = [
        "# Research Context (Restored from Checkpoint)\n",
        f"*Checkpoint: {checkpoint.id}*\n",
        f"*Saved: {checkpoint.ts[:16].replace('T', ' ')} | Confidence: {checkpoint.confidence:.0%}*\n\n",
        "## Core Question\n",
        f"{checkpoint.core_question}\n\n",
        "## Current Thesis\n",
        f"{checkpoint.thesis}\n\n",
    ]

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

    return "".join(parts)


def create_checkpoint_from_dict(data: dict, trigger: str = "manual") -> Checkpoint:
    """Create a Checkpoint from a dictionary (e.g., parsed from Claude's output)."""
    ts = datetime.now(UTC).isoformat()

    # Generate ID
    description = data.get("thesis", "checkpoint")[:50]
    checkpoint_id = generate_checkpoint_id(description)

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
        action_goal=data.get("action", {}).get("goal", ""),
        action_type=data.get("action", {}).get("type", ""),
    )
