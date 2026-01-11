"""Checkpoint system for Sage.

Saves and restores semantic research state across sessions.
Checkpoints are stored as YAML files in ~/.sage/checkpoints/ or .sage/checkpoints/.
"""

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from sage.config import SAGE_DIR


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
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
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


def save_checkpoint(checkpoint: Checkpoint, project_path: Path | None = None) -> Path:
    """Save a checkpoint to disk."""
    checkpoints_dir = ensure_checkpoints_dir(project_path)

    # Convert to dict for YAML
    data = {
        "checkpoint": {
            "id": checkpoint.id,
            "ts": checkpoint.ts,
            "trigger": checkpoint.trigger,
            "core_question": checkpoint.core_question,
            "thesis": checkpoint.thesis,
            "confidence": checkpoint.confidence,
            "open_questions": checkpoint.open_questions,
            "sources": [asdict(s) for s in checkpoint.sources],
            "tensions": [
                {"between": list(t.between), "nature": t.nature, "resolution": t.resolution}
                for t in checkpoint.tensions
            ],
            "unique_contributions": [asdict(c) for c in checkpoint.unique_contributions],
            "action": {
                "goal": checkpoint.action_goal,
                "type": checkpoint.action_type,
            },
            "metadata": {
                "skill": checkpoint.skill,
                "project": checkpoint.project,
                "parent_checkpoint": checkpoint.parent_checkpoint,
                "message_count": checkpoint.message_count,
                "token_estimate": checkpoint.token_estimate,
            },
        }
    }

    file_path = checkpoints_dir / f"{checkpoint.id}.yaml"
    with open(file_path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return file_path


def load_checkpoint(checkpoint_id: str, project_path: Path | None = None) -> Checkpoint | None:
    """Load a checkpoint by ID."""
    checkpoints_dir = get_checkpoints_dir(project_path)
    file_path = checkpoints_dir / f"{checkpoint_id}.yaml"

    if not file_path.exists():
        # Try partial match
        matches = list(checkpoints_dir.glob(f"*{checkpoint_id}*.yaml"))
        if len(matches) == 1:
            file_path = matches[0]
        elif len(matches) > 1:
            return None  # Ambiguous
        else:
            return None

    return _load_checkpoint_file(file_path)


def _load_checkpoint_file(file_path: Path) -> Checkpoint | None:
    """Load a checkpoint from a file path."""
    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)

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
    """List checkpoints, most recent first."""
    checkpoints_dir = get_checkpoints_dir(project_path)

    if not checkpoints_dir.exists():
        return []

    checkpoints = []
    for file_path in sorted(checkpoints_dir.glob("*.yaml"), reverse=True):
        cp = _load_checkpoint_file(file_path)
        if cp:
            if skill and cp.skill != skill:
                continue
            checkpoints.append(cp)
            if len(checkpoints) >= limit:
                break

    return checkpoints


def delete_checkpoint(checkpoint_id: str, project_path: Path | None = None) -> bool:
    """Delete a checkpoint by ID."""
    checkpoints_dir = get_checkpoints_dir(project_path)
    file_path = checkpoints_dir / f"{checkpoint_id}.yaml"

    if not file_path.exists():
        # Try partial match
        matches = list(checkpoints_dir.glob(f"*{checkpoint_id}*.yaml"))
        if len(matches) == 1:
            file_path = matches[0]
        else:
            return False

    file_path.unlink()
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
    ts = datetime.now(timezone.utc).isoformat()

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
