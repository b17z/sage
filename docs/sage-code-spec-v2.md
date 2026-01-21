# Sage v2.0 Code Spec

**Purpose:** Implementation guide for Claude Code. Load this, not the full research spec.

**Full spec:** `sage-memory-framework-v2.5.md` (reference only when design rationale needed)

---

## Testing Requirements

**CRITICAL: Every feature implementation MUST include:**

1. **Unit tests** — Test individual functions in isolation
2. **Integration tests** — Test feature workflows end-to-end
3. **Edge case tests** — Empty inputs, malformed data, boundary conditions

**Current test count:** 578 tests
**Target:** Maintain or increase coverage with every PR

**Test patterns:**

```python
# Unit test example
def test_topic_drift_detection_below_threshold():
    """Topic drift triggers when similarity drops below threshold."""
    detector = StructuralDetector(config={"topic_drift_threshold": 0.5})

    # Simulate conversation about topic A
    for msg in TOPIC_A_MESSAGES:
        detector.analyze_message(msg, role="user")

    # Sudden shift to topic B
    triggers = detector.analyze_message(TOPIC_B_MESSAGE, role="user")

    assert len(triggers) == 1
    assert triggers[0].type == "topic_shift"
    assert triggers[0].confidence > 0.5


# Integration test example
def test_checkpoint_created_on_topic_shift():
    """Full flow: topic shift detected → checkpoint saved."""
    session = create_test_session()

    # Build up conversation
    for msg in TOPIC_A_MESSAGES:
        session.add_message(msg)

    # Trigger topic shift
    session.add_message(TOPIC_B_MESSAGE)

    # Verify checkpoint created
    checkpoints = session.get_checkpoints()
    assert len(checkpoints) == 1
    assert checkpoints[0].trigger == "topic_shift"


# Edge case example
def test_empty_message_buffer_no_crash():
    """Structural detector handles empty buffer gracefully."""
    detector = StructuralDetector(config={})
    triggers = detector.analyze_message("Hello", role="user")
    assert triggers == []  # No crash, no false triggers
```

**Before marking any feature complete:**

```bash
# Run full test suite
pytest tests/ -v

# Check coverage
pytest tests/ --cov=sage --cov-report=term-missing

# Integration tests specifically
pytest tests/integration/ -v
```

---

## v2.0 Scope

### 1. Embedding Model Upgrade

**File:** `sage/embeddings.py`

```python
# Change
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# To
DEFAULT_MODEL = "mixedbread-ai/mxbai-embed-large-v1"

# Add query prefix function
def get_query_embedding(text: str) -> np.ndarray:
    """Embed a query with mxbai's required prefix."""
    prefixed = f"Represent this sentence for searching relevant passages: {text}"
    return get_embedding(prefixed)
```

**Tests required:**
- [ ] `test_query_embedding_has_prefix`
- [ ] `test_document_embedding_no_prefix`
- [ ] `test_similarity_scores_in_expected_range`
- [ ] `test_rebuild_embeddings_after_model_swap`

---

### 2. Config System

**New file:** `sage/config.py`

```python
from dataclasses import dataclass, field
from pathlib import Path
import yaml

@dataclass
class SageConfig:
    """User-configurable parameters with sensible defaults."""

    # Retrieval
    recall_threshold: float = 0.70
    dedup_threshold: float = 0.90
    embedding_weight: float = 0.70
    keyword_weight: float = 0.30

    # Structural detection
    topic_drift_threshold: float = 0.50
    convergence_question_drop: float = 0.20
    depth_min_messages: int = 8
    depth_min_tokens: int = 2000

    # Embedding
    embedding_model: str = "mixedbread-ai/mxbai-embed-large-v1"

    @classmethod
    def load(cls, sage_dir: Path) -> "SageConfig":
        """Load config with user → project override cascade."""
        config_path = sage_dir / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                overrides = yaml.safe_load(f) or {}
            return cls(**{k: v for k, v in overrides.items() if hasattr(cls, k)})
        return cls()

    def save(self, sage_dir: Path):
        """Persist config to YAML."""
        config_path = sage_dir / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(self.__dict__, f, default_flow_style=False)


def get_config() -> SageConfig:
    """Load config with project → user → default cascade."""
    # Check project-level first
    project_sage = Path.cwd() / ".sage"
    if project_sage.exists():
        project_config = SageConfig.load(project_sage)
        # Could merge with user-level here
        return project_config

    # Fall back to user-level
    user_sage = Path.home() / ".sage"
    return SageConfig.load(user_sage)
```

**CLI commands:**

```python
# In sage/cli.py

@cli.group()
def config():
    """Manage Sage configuration."""
    pass

@config.command("list")
def config_list():
    """Show current configuration."""
    cfg = get_config()
    for key, value in cfg.__dict__.items():
        click.echo(f"{key}: {value}")

@config.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--project", is_flag=True, help="Set in project config")
def config_set(key: str, value: str, project: bool):
    """Set a configuration value."""
    cfg = get_config()
    if not hasattr(cfg, key):
        raise click.BadParameter(f"Unknown config key: {key}")

    # Type coercion
    current = getattr(cfg, key)
    if isinstance(current, float):
        value = float(value)
    elif isinstance(current, int):
        value = int(value)

    setattr(cfg, key, value)

    sage_dir = Path.cwd() / ".sage" if project else Path.home() / ".sage"
    cfg.save(sage_dir)
    click.echo(f"Set {key} = {value}")

@config.command("reset")
@click.argument("key", required=False)
@click.option("--all", is_flag=True, help="Reset all to defaults")
def config_reset(key: str | None, all: bool):
    """Reset configuration to defaults."""
    if all:
        sage_dir = Path.home() / ".sage"
        (sage_dir / "config.yaml").unlink(missing_ok=True)
        click.echo("Reset all config to defaults")
    elif key:
        cfg = get_config()
        default = SageConfig()
        setattr(cfg, key, getattr(default, key))
        cfg.save(Path.home() / ".sage")
        click.echo(f"Reset {key} to {getattr(default, key)}")
```

**Tests required:**
- [ ] `test_config_load_defaults`
- [ ] `test_config_load_from_yaml`
- [ ] `test_config_project_overrides_user`
- [ ] `test_config_set_persists`
- [ ] `test_config_reset_single_key`
- [ ] `test_config_reset_all`
- [ ] `test_config_type_coercion`
- [ ] `test_config_unknown_key_error`

---

### 3. Knowledge Debug Command

**File:** `sage/cli.py`

```python
@knowledge.command("debug")
@click.argument("query")
def knowledge_debug(query: str):
    """Debug knowledge retrieval for a query."""
    cfg = get_config()

    click.echo(f"Query: \"{query}\"")
    click.echo(f"Config: recall_threshold={cfg.recall_threshold}, "
               f"embedding_weight={cfg.embedding_weight}, "
               f"keyword_weight={cfg.keyword_weight}")
    click.echo()

    # Get all scores (not just above threshold)
    all_scores = get_all_knowledge_scores(query)

    above = [(k, s) for k, s in all_scores if s.combined >= cfg.recall_threshold]
    near_miss = [(k, s) for k, s in all_scores
                 if cfg.recall_threshold - 0.10 <= s.combined < cfg.recall_threshold]

    if above:
        click.echo(f"Would retrieve (above {cfg.recall_threshold}):")
        for k, s in above:
            click.echo(f"  ✓ {k.id:<30} combined={s.combined:.3f}  "
                      f"(emb={s.embedding:.2f}, kw={s.keyword:.2f})")
    else:
        click.echo("No matches above threshold.")

    click.echo()

    if near_miss:
        click.echo(f"Near misses ({cfg.recall_threshold - 0.10:.2f} - {cfg.recall_threshold}):")
        for k, s in near_miss:
            click.echo(f"  ✗ {k.id:<30} combined={s.combined:.3f}  "
                      f"(emb={s.embedding:.2f}, kw={s.keyword:.2f})")

        # Suggest threshold adjustment
        highest_miss = max(s.combined for _, s in near_miss)
        suggested = round(highest_miss - 0.01, 2)
        click.echo()
        click.echo(f"Tip: `sage config set recall_threshold {suggested}` "
                  f"would include {len(near_miss)} more item(s)")
```

**Tests required:**
- [ ] `test_debug_shows_above_threshold`
- [ ] `test_debug_shows_near_misses`
- [ ] `test_debug_shows_tip_when_near_misses_exist`
- [ ] `test_debug_no_tip_when_no_near_misses`
- [ ] `test_debug_empty_knowledge_base`

---

### 4. Checkpoint key_evidence Field

**File:** `sage/checkpoint.py`

```python
@dataclass
class Checkpoint:
    id: str
    timestamp: datetime
    trigger: str

    # Core content
    core_question: str
    thesis: str
    confidence: float

    # NEW: Evidence and reasoning
    key_evidence: list[str] = field(default_factory=list)
    reasoning_trace: str = ""

    # Existing fields
    open_questions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    token_count: int = 0
```

**Update MCP tool:**

```python
# In sage/mcp_server.py

@mcp_tool
def sage_save_checkpoint(
    thesis: str,
    confidence: float,
    trigger: str,
    core_question: str = "",
    key_evidence: list[str] | None = None,  # NEW
    reasoning_trace: str = "",               # NEW
    open_questions: list[str] | None = None,
    sources: list[str] | None = None,
) -> SaveResult:
    """Save a checkpoint with optional evidence and reasoning."""
    checkpoint = Checkpoint(
        id=generate_checkpoint_id(thesis),
        timestamp=datetime.now(UTC),
        trigger=trigger,
        core_question=core_question,
        thesis=thesis,
        confidence=confidence,
        key_evidence=key_evidence or [],
        reasoning_trace=reasoning_trace,
        open_questions=open_questions or [],
        sources=sources or [],
    )
    return save_checkpoint(checkpoint)
```

**Tests required:**
- [ ] `test_checkpoint_with_key_evidence`
- [ ] `test_checkpoint_without_key_evidence_backwards_compat`
- [ ] `test_checkpoint_load_displays_evidence`
- [ ] `test_mcp_tool_accepts_key_evidence`

---

### 5. Structural Trigger Detection (v2.1)

**New file:** `sage/triggers/structural.py`

```python
from dataclasses import dataclass
import numpy as np
from sage.embeddings import get_embedding, cosine_similarity
from sage.config import SageConfig

@dataclass
class MessageBuffer:
    content: str
    embedding: np.ndarray
    role: str
    is_question: bool

@dataclass
class Trigger:
    type: str  # topic_shift, synthesis, branch_point, constraint
    confidence: float
    source: str  # structural, linguistic, claude_behavior, adaptive
    reason: str

class StructuralDetector:
    def __init__(self, config: SageConfig):
        self.config = config
        self.buffer: list[MessageBuffer] = []

    def analyze_message(self, content: str, role: str) -> list[Trigger]:
        """Detect structural inflection points."""
        triggers = []
        embedding = get_embedding(content)
        is_question = self._is_question(content)

        if len(self.buffer) >= 5:
            # Topic drift detection
            drift_trigger = self._detect_topic_drift(embedding)
            if drift_trigger:
                triggers.append(drift_trigger)

            # Convergence detection (questions → statements)
            if role == "user":
                conv_trigger = self._detect_convergence(is_question)
                if conv_trigger:
                    triggers.append(conv_trigger)

        # Update buffer
        self.buffer.append(MessageBuffer(
            content=content,
            embedding=embedding,
            role=role,
            is_question=is_question
        ))

        # Keep buffer bounded
        if len(self.buffer) > 50:
            self.buffer = self.buffer[-50:]

        return triggers

    def _detect_topic_drift(self, current_embedding: np.ndarray) -> Trigger | None:
        """Detect topic shift via embedding similarity."""
        recent = self.buffer[-5:]
        centroid = np.mean([m.embedding for m in recent], axis=0)
        similarity = cosine_similarity(current_embedding, centroid)

        if similarity < self.config.topic_drift_threshold:
            return Trigger(
                type="topic_shift",
                confidence=1 - similarity,  # Lower similarity = higher confidence
                source="structural",
                reason=f"Topic similarity dropped to {similarity:.2f}"
            )
        return None

    def _detect_convergence(self, current_is_question: bool) -> Trigger | None:
        """Detect shift from questions to statements."""
        recent_user = [m for m in self.buffer[-10:] if m.role == "user"]
        if len(recent_user) < 5:
            return None

        early = recent_user[:len(recent_user)//2]
        late = recent_user[len(recent_user)//2:]

        early_q_ratio = sum(1 for m in early if m.is_question) / len(early)
        late_q_ratio = sum(1 for m in late if m.is_question) / len(late)

        # Significant drop in questions + current is statement
        if early_q_ratio > 0.5 and late_q_ratio < 0.2 and not current_is_question:
            return Trigger(
                type="synthesis",
                confidence=0.7,
                source="structural",
                reason="Shift from questions to statements"
            )
        return None

    def _is_question(self, text: str) -> bool:
        """Simple question detection."""
        text = text.strip()
        if text.endswith("?"):
            return True
        question_starters = ("what", "how", "why", "when", "where", "who",
                           "is", "are", "can", "could", "should", "would", "do", "does")
        return text.lower().startswith(question_starters)
```

**Tests required:**
- [ ] `test_topic_drift_triggers_on_low_similarity`
- [ ] `test_topic_drift_no_trigger_on_high_similarity`
- [ ] `test_convergence_triggers_on_question_drop`
- [ ] `test_convergence_no_trigger_early_conversation`
- [ ] `test_buffer_bounded_at_50`
- [ ] `test_empty_buffer_no_crash`
- [ ] `test_structural_uses_config_thresholds`

---

### 6. Trigger Signal Hierarchy

**New file:** `sage/triggers/combiner.py`

```python
def should_trigger(
    structural: Trigger | None,
    linguistic: Trigger | None
) -> Trigger | None:
    """
    Combine structural and linguistic signals.

    Structural signals INITIATE triggers.
    Linguistic signals CONFIRM but don't initiate alone.
    """
    # High-confidence structural alone = trigger
    if structural and structural.confidence > 0.8:
        return structural

    # Linguistic alone = NOT enough (too noisy)
    if linguistic and not structural:
        return None

    # Structural + linguistic = trigger with boosted confidence
    if structural and linguistic:
        if structural.confidence > 0.5:
            return Trigger(
                type=structural.type,
                confidence=min(0.95, structural.confidence + 0.2),
                source="structural+linguistic",
                reason=f"{structural.reason}; confirmed by '{linguistic.reason}'"
            )

    return None
```

**Tests required:**
- [ ] `test_high_confidence_structural_triggers_alone`
- [ ] `test_linguistic_alone_does_not_trigger`
- [ ] `test_structural_plus_linguistic_boosts_confidence`
- [ ] `test_low_confidence_structural_alone_no_trigger`
- [ ] `test_confidence_capped_at_095`

---

## Documentation Updates

| Doc | Purpose | Priority |
|-----|---------|----------|
| `README.md` | Overhaul — currently stale | v2.0 |
| `docs/ARCHITECTURE.md` | System design | v2.0 |
| `docs/FEATURES.md` | User-facing features | v2.0 |
| `docs/ROADMAP.md` | Version timeline | v2.0 |

---

## Migration Checklist

- [ ] Run `sage admin rebuild-embeddings` after model swap
- [ ] Verify existing checkpoints load with new schema
- [ ] Config file created on first `sage config` command
- [ ] All 91+ tests passing before merge

---

## v2.x Fortification (from Code Audit)

Based on the January 2026 engineering principles audit. These are improvements to strengthen the codebase.

### 7. Structured Logging

**New file:** `sage/logging.py`

**Principle:** "You can't fix what you can't see." — SRE perspective

```python
import json
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "extra"):
            log_entry.update(record.extra)

        return json.dumps(log_entry)


def get_logger(name: str) -> logging.Logger:
    """Get a structured logger instance."""
    logger = logging.getLogger(f"sage.{name}")

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger


def log_operation(
    logger: logging.Logger,
    operation: str,
    **context: Any
) -> None:
    """Log an operation with context."""
    logger.info(operation, extra={"operation": operation, **context})
```

**Usage in modules:**

```python
# In sage/checkpoint.py
from sage.logging import get_logger, log_operation

logger = get_logger("checkpoint")

def save_checkpoint(checkpoint: Checkpoint, project_path: Path) -> Result[Path, SageError]:
    start = time.perf_counter()

    # ... save logic ...

    log_operation(logger, "checkpoint_saved",
        checkpoint_id=checkpoint.id,
        duration_ms=int((time.perf_counter() - start) * 1000),
        size_bytes=len(content),
        trigger=checkpoint.trigger,
    )
    return ok(path)
```

**Tests required:**
- [ ] `test_structured_formatter_outputs_json`
- [ ] `test_log_operation_includes_context`
- [ ] `test_logger_singleton_per_module`

---

### 8. Health Check Command

**File:** `sage/cli.py`

**Principle:** "Health checks expose dependency status." — SRE perspective

```python
@cli.command("health")
def health_check():
    """Deep health check of Sage components."""
    checks = {}

    # Config validity
    try:
        cfg = get_sage_config()
        checks["config"] = {"status": "ok", "embedding_model": cfg.embedding_model}
    except Exception as e:
        checks["config"] = {"status": "error", "error": str(e)}

    # Embedding model loadable
    try:
        from sage.embeddings import get_model, is_available
        if not is_available():
            checks["embeddings"] = {"status": "unavailable", "reason": "sentence-transformers not installed"}
        else:
            result = get_model()
            if result.is_ok():
                model = result.unwrap()
                checks["embeddings"] = {
                    "status": "ok",
                    "model": cfg.embedding_model,
                    "dimension": model.get_sentence_embedding_dimension(),
                }
            else:
                checks["embeddings"] = {"status": "error", "error": result.unwrap_err().message}
    except Exception as e:
        checks["embeddings"] = {"status": "error", "error": str(e)}

    # Knowledge index valid
    try:
        from sage.knowledge import load_knowledge_index
        result = load_knowledge_index()
        if result.is_ok():
            index = result.unwrap()
            checks["knowledge"] = {"status": "ok", "item_count": len(index.items)}
        else:
            checks["knowledge"] = {"status": "error", "error": result.unwrap_err().message}
    except Exception as e:
        checks["knowledge"] = {"status": "error", "error": str(e)}

    # Disk space for embeddings
    try:
        from sage.config import SAGE_DIR
        import shutil
        usage = shutil.disk_usage(SAGE_DIR)
        free_gb = usage.free / (1024 ** 3)
        checks["disk"] = {
            "status": "ok" if free_gb > 1.0 else "warning",
            "free_gb": round(free_gb, 2),
        }
    except Exception as e:
        checks["disk"] = {"status": "error", "error": str(e)}

    # Output
    overall = "healthy" if all(c.get("status") == "ok" for c in checks.values()) else "degraded"

    console = Console()
    console.print(f"\n[bold]Sage Health Check[/bold]: {overall}\n")

    for component, result in checks.items():
        status = result.pop("status")
        icon = "✓" if status == "ok" else "⚠" if status == "warning" else "✗"
        color = "green" if status == "ok" else "yellow" if status == "warning" else "red"

        console.print(f"[{color}]{icon}[/{color}] {component}: {status}")
        for key, value in result.items():
            console.print(f"    {key}: {value}")

    return 0 if overall == "healthy" else 1
```

**Tests required:**
- [ ] `test_health_check_all_ok`
- [ ] `test_health_check_missing_embeddings`
- [ ] `test_health_check_invalid_config`
- [ ] `test_health_check_low_disk_warning`

---

### 9. Atomic File Writes

**File:** `sage/utils.py` (new)

**Principle:** "What happens if this fails?" — Backend engineer perspective

```python
from pathlib import Path
import tempfile
import os

def atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    """
    Write content to file atomically using temp file + rename.

    This prevents partial writes if the process is interrupted.
    On POSIX systems, rename() is atomic within the same filesystem.
    """
    # Create temp file in same directory (same filesystem)
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix=".tmp_", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)

        os.chmod(temp_path, mode)
        os.rename(temp_path, path)  # Atomic on POSIX
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def atomic_write_bytes(path: Path, content: bytes, mode: int = 0o644) -> None:
    """Binary version of atomic_write."""
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix=".tmp_", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)

        os.chmod(temp_path, mode)
        os.rename(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
```

**Update checkpoint.py:**

```python
# Before
path.write_text(content)

# After
from sage.utils import atomic_write
atomic_write(path, content, mode=0o644)
```

**Tests required:**
- [ ] `test_atomic_write_creates_file`
- [ ] `test_atomic_write_no_partial_on_interrupt`
- [ ] `test_atomic_write_preserves_permissions`
- [ ] `test_atomic_write_cleans_temp_on_failure`

---

### 10. CLI Modularization

**Principle:** "Single file per concept when complex." — Code organization

**Current:** `cli.py` at 1,500+ lines

**Proposed structure:**

```
sage/
├── cli/
│   ├── __init__.py       # Main entry, Click group
│   ├── core.py           # init, new, rm, ask, list, show, context
│   ├── checkpoint.py     # checkpoint list, show, restore, rm
│   ├── knowledge.py      # knowledge add, list, rm, match, debug
│   ├── config.py         # config list, set, reset
│   ├── admin.py          # rebuild-embeddings, clear-cache, health
│   ├── hooks.py          # hooks install, uninstall, status
│   ├── mcp.py            # mcp install, uninstall, status
│   └── templates.py      # templates list, show
```

**Implementation pattern:**

```python
# sage/cli/__init__.py
import click
from sage.cli.core import core_commands
from sage.cli.checkpoint import checkpoint_group
from sage.cli.knowledge import knowledge_group
from sage.cli.config import config_group
from sage.cli.admin import admin_group

@click.group()
def cli():
    """Sage - Semantic checkpointing for AI research."""
    pass

# Register command groups
cli.add_command(checkpoint_group, name="checkpoint")
cli.add_command(knowledge_group, name="knowledge")
cli.add_command(config_group, name="config")
cli.add_command(admin_group, name="admin")

# Register top-level commands
for cmd in core_commands:
    cli.add_command(cmd)

def main():
    cli()
```

```python
# sage/cli/checkpoint.py
import click

@click.group()
def checkpoint_group():
    """Manage research checkpoints."""
    pass

@checkpoint_group.command("list")
@click.option("--limit", default=10)
def checkpoint_list(limit: int):
    """List saved checkpoints."""
    ...

@checkpoint_group.command("show")
@click.argument("checkpoint_id")
def checkpoint_show(checkpoint_id: str):
    """Show checkpoint details."""
    ...
```

**Migration:**
- [ ] Create `sage/cli/` directory
- [ ] Extract checkpoint commands to `checkpoint.py`
- [ ] Extract knowledge commands to `knowledge.py`
- [ ] Extract config commands to `config.py`
- [ ] Extract admin commands to `admin.py`
- [ ] Update imports in `__init__.py`
- [ ] Verify all tests pass
- [ ] Delete old `cli.py`

---

### 11. Branded Types (Optional Enhancement)

**File:** `sage/types.py` (new)

**Principle:** "Branded types prevent mixing up IDs." — Type safety

```python
from typing import NewType

# Branded ID types
CheckpointId = NewType("CheckpointId", str)
KnowledgeId = NewType("KnowledgeId", str)
SkillName = NewType("SkillName", str)

# Constructors with validation
def checkpoint_id(raw: str) -> CheckpointId:
    """Create a validated checkpoint ID."""
    if not raw or not isinstance(raw, str):
        raise ValueError(f"Invalid checkpoint ID: {raw}")
    return CheckpointId(raw)

def knowledge_id(raw: str) -> KnowledgeId:
    """Create a validated knowledge ID."""
    if not raw or not isinstance(raw, str):
        raise ValueError(f"Invalid knowledge ID: {raw}")
    return KnowledgeId(raw)
```

**Usage:**

```python
# Before
def load_checkpoint(id: str) -> Result[Checkpoint, SageError]: ...

# After
from sage.types import CheckpointId
def load_checkpoint(id: CheckpointId) -> Result[Checkpoint, SageError]: ...

# Prevents
load_checkpoint(knowledge_id)  # Type error at IDE level
```

**Tests required:**
- [ ] `test_checkpoint_id_validates`
- [ ] `test_knowledge_id_validates`
- [ ] `test_type_mismatch_caught` (mypy)

---

## v2.4 Token Economics (from User Feedback)

Track and display token savings — a key selling point.

### 12. Token Savings Tracking

**File:** `sage/usage.py` (extend existing)

**Principle:** "If you can't measure it, you can't sell it."

```python
@dataclass
class SessionSavings:
    """Token savings from checkpoint restore vs full replay."""
    session_id: str
    full_context_tokens: int      # What full replay would cost
    checkpoint_tokens: int         # What checkpoint restore cost
    knowledge_tokens: int          # Knowledge items injected
    savings_tokens: int            # full - (checkpoint + knowledge)
    savings_percent: float         # savings / full * 100
    estimated_cost_saved: float    # At ~$3/1M tokens

def calculate_savings(
    checkpoint: Checkpoint,
    recalled_knowledge: list[KnowledgeItem],
    estimated_full_context: int = 100_000  # Conservative default
) -> SessionSavings:
    """Calculate token savings from using checkpoint vs full replay."""
    checkpoint_tokens = estimate_tokens(format_checkpoint_for_context(checkpoint))
    knowledge_tokens = sum(estimate_tokens(k.content) for k in recalled_knowledge)

    restore_tokens = checkpoint_tokens + knowledge_tokens
    savings = estimated_full_context - restore_tokens

    return SessionSavings(
        session_id=checkpoint.id,
        full_context_tokens=estimated_full_context,
        checkpoint_tokens=checkpoint_tokens,
        knowledge_tokens=knowledge_tokens,
        savings_tokens=savings,
        savings_percent=(savings / estimated_full_context) * 100,
        estimated_cost_saved=(savings / 1_000_000) * 3.00  # ~$3/1M tokens
    )
```

**CLI command:**

```python
@usage.command("savings")
@click.option("--since", default="30d", help="Time period (7d, 30d, all)")
def usage_savings(since: str):
    """Show token savings from checkpoint usage."""
    savings = load_savings_history(since)

    console.print("\n[bold]Token Savings Report[/bold]\n")

    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    total_saved = sum(s.savings_tokens for s in savings)
    total_cost_saved = sum(s.estimated_cost_saved for s in savings)
    avg_compression = sum(s.savings_percent for s in savings) / len(savings) if savings else 0

    table.add_row("Checkpoints restored", str(len(savings)))
    table.add_row("Tokens saved", f"{total_saved:,}")
    table.add_row("Avg compression", f"{avg_compression:.1f}%")
    table.add_row("Est. cost saved", f"${total_cost_saved:.2f}")

    console.print(table)

    # Show breakdown
    console.print("\n[dim]Savings = full context replay - (checkpoint + knowledge)[/dim]")
    console.print("[dim]Cost estimate at $3/1M tokens (Claude Sonnet)[/dim]")
```

**MCP tool:**

```python
@mcp.tool()
def sage_session_savings() -> str:
    """Get token savings summary for current session."""
    # Return formatted savings for display
```

**Tests required:**
- [ ] `test_savings_calculation_correct`
- [ ] `test_savings_percent_bounded`
- [ ] `test_savings_history_persistence`
- [ ] `test_cli_savings_output`

---

## v2.5 Code-Aware Intelligence (from User Feedback)

Extend Sage from research-only to code+research hybrid.

### 13. Code-Aware Triggers

**File:** `sage/triggers/code.py` (new)

**Principle:** "Code semantics differ from research semantics."

```python
from dataclasses import dataclass
import re

@dataclass
class CodeTrigger:
    type: str  # refactor, architecture, test_change, dependency_update
    confidence: float
    files_affected: list[str]
    reason: str

class CodeDetector:
    """Detect code-significant moments from conversation."""

    # Patterns indicating code changes
    REFACTOR_PATTERNS = [
        r"refactor(?:ed|ing)?",
        r"extract(?:ed|ing)?\s+(?:to|into)",
        r"moved?\s+(?:to|from)",
        r"rename(?:d|ing)?",
        r"split(?:ting)?\s+(?:into|out)",
    ]

    ARCHITECTURE_PATTERNS = [
        r"architecture",
        r"design\s+decision",
        r"(?:add|create|implement)(?:ed|ing)?\s+(?:new\s+)?(?:module|service|layer)",
        r"database\s+schema",
        r"api\s+(?:design|contract)",
    ]

    TEST_PATTERNS = [
        r"(?:add|write|update)(?:ed|ing)?\s+tests?",
        r"test\s+coverage",
        r"(?:fix|update)(?:ed|ing)?\s+(?:failing|broken)\s+tests?",
    ]

    def analyze(self, content: str, files_mentioned: list[str]) -> CodeTrigger | None:
        """Detect code-significant trigger from message content."""
        content_lower = content.lower()

        # Check refactor patterns
        if any(re.search(p, content_lower) for p in self.REFACTOR_PATTERNS):
            return CodeTrigger(
                type="refactor",
                confidence=0.7,
                files_affected=files_mentioned,
                reason="Refactoring detected"
            )

        # Check architecture patterns
        if any(re.search(p, content_lower) for p in self.ARCHITECTURE_PATTERNS):
            return CodeTrigger(
                type="architecture",
                confidence=0.8,
                files_affected=files_mentioned,
                reason="Architecture decision detected"
            )

        # Check test patterns
        if any(re.search(p, content_lower) for p in self.TEST_PATTERNS):
            return CodeTrigger(
                type="test_change",
                confidence=0.6,
                files_affected=files_mentioned,
                reason="Test changes detected"
            )

        return None
```

**Tests required:**
- [ ] `test_refactor_detection`
- [ ] `test_architecture_detection`
- [ ] `test_test_change_detection`
- [ ] `test_no_false_positives_on_discussion`

---

### 14. Engineering Principles MCP

**File:** `sage/mcp_principles.py` (new, or separate package)

**Principle:** "Why read a doc when Claude can query it?"

```python
from pathlib import Path
from sage.embeddings import get_query_embedding, find_similar

# Load and embed principles on startup
PRINCIPLES_PATH = Path.home() / "engineering_principles"

@dataclass
class PrincipleSection:
    title: str
    content: str
    embedding: np.ndarray

def load_principles() -> list[PrincipleSection]:
    """Load and embed engineering principles."""
    sections = []
    for file in PRINCIPLES_PATH.glob("*.md"):
        content = file.read_text()
        # Split by ## headers
        for section in split_by_headers(content):
            sections.append(PrincipleSection(
                title=section.title,
                content=section.content,
                embedding=get_embedding(section.content).unwrap()
            ))
    return sections

@mcp.tool()
def query_engineering_principles(
    topic: str,
    limit: int = 3
) -> str:
    """
    Search engineering principles for guidance on a topic.

    Args:
        topic: What you need guidance on (e.g., "error handling", "database design")
        limit: Number of relevant sections to return

    Returns:
        Relevant principle sections with context
    """
    query_emb = get_query_embedding(topic).unwrap()
    matches = find_similar(query_emb, principles_store, top_k=limit)

    result = f"## Engineering Principles: {topic}\n\n"
    for match in matches:
        section = get_section(match.id)
        result += f"### {section.title} ({match.score:.0%} relevant)\n\n"
        result += section.content + "\n\n"

    return result


@mcp.tool()
def senior_engineer_review(
    description: str,
    personas: list[str] | None = None
) -> str:
    """
    Get feedback from senior engineer perspectives.

    Args:
        description: What you're building/changing
        personas: Which perspectives to include.
                  Options: security, backend, performance, data, devops, product
                  Default: all applicable

    Returns:
        Structured feedback from each persona's perspective
    """
    available_personas = {
        "security": SECURITY_ENGINEER_PROMPT,
        "backend": BACKEND_ENGINEER_PROMPT,
        "performance": PERFORMANCE_ENGINEER_PROMPT,
        "data": DATA_ENGINEER_PROMPT,
        "devops": DEVOPS_ENGINEER_PROMPT,
        "product": PRODUCT_ENGINEER_PROMPT,
    }

    selected = personas or list(available_personas.keys())

    result = f"## Senior Engineer Review\n\n"
    result += f"**Reviewing:** {description}\n\n"

    for persona in selected:
        if persona in available_personas:
            questions = get_persona_questions(persona)
            result += f"### {persona.title()} Engineer\n\n"
            result += f"**Key questions:**\n"
            for q in questions[:5]:
                result += f"- {q}\n"
            result += "\n"

    return result
```

**Tests required:**
- [ ] `test_query_principles_returns_relevant`
- [ ] `test_senior_review_includes_personas`
- [ ] `test_unknown_persona_ignored`

---

### 15. Knowledge Edit & Deprecation

**File:** `sage/knowledge.py` (extend)

**Principle:** "Wrong knowledge is worse than no knowledge."

```python
@dataclass
class KnowledgeStatus:
    ACTIVE = "active"
    DEPRECATED = "deprecated"  # Still searchable, marked as outdated
    ARCHIVED = "archived"      # Hidden from recall

def update_knowledge(
    knowledge_id: str,
    content: str | None = None,
    keywords: list[str] | None = None,
    status: str | None = None,
    deprecation_note: str | None = None
) -> Result[KnowledgeItem, SageError]:
    """
    Update knowledge item in place.

    - content: New content (re-embeds if changed)
    - keywords: New keywords (replaces existing)
    - status: active, deprecated, archived
    - deprecation_note: Why this was deprecated
    """
    item = load_knowledge_item(knowledge_id)
    if item.is_err():
        return item

    current = item.unwrap()

    # Track history
    history_entry = {
        "ts": datetime.now(UTC).isoformat(),
        "previous_content": current.content if content else None,
        "change": "content" if content else "status" if status else "keywords"
    }

    updated = KnowledgeItem(
        id=current.id,
        content=content or current.content,
        keywords=keywords or current.keywords,
        status=status or current.status,
        deprecation_note=deprecation_note,
        history=[*current.history, history_entry],
        # ... other fields
    )

    # Re-embed if content changed
    if content and content != current.content:
        new_embedding = get_embedding(content)
        update_knowledge_embedding(knowledge_id, new_embedding.unwrap())

    return save_knowledge_item(updated)


def deprecate_knowledge(
    knowledge_id: str,
    reason: str,
    replacement_id: str | None = None
) -> Result[None, SageError]:
    """
    Mark knowledge as deprecated with reason.

    Deprecated items:
    - Still appear in search results (marked as deprecated)
    - Show deprecation warning when recalled
    - Can point to replacement
    """
    return update_knowledge(
        knowledge_id,
        status=KnowledgeStatus.DEPRECATED,
        deprecation_note=f"{reason}" + (f" See: {replacement_id}" if replacement_id else "")
    )
```

**CLI commands:**

```bash
sage knowledge edit <id> --content "new content"
sage knowledge edit <id> --keywords new,keywords
sage knowledge deprecate <id> --reason "Outdated, use X instead" --replacement <new-id>
sage knowledge archive <id>  # Hide from recall entirely
```

**MCP tool:**

```python
@mcp.tool()
def sage_update_knowledge(
    knowledge_id: str,
    content: str | None = None,
    keywords: list[str] | None = None,
    deprecate: bool = False,
    deprecation_reason: str | None = None
) -> str:
    """Update or deprecate existing knowledge."""
```

**Tests required:**
- [ ] `test_knowledge_edit_preserves_history`
- [ ] `test_deprecated_shows_warning`
- [ ] `test_archived_not_recalled`
- [ ] `test_edit_reembeds_on_content_change`

---

## Quick Reference

**Load config:**
```python
from sage.config import get_config
cfg = get_config()
```

**Use query embedding:**
```python
from sage.embeddings import get_query_embedding
query_emb = get_query_embedding("morpho curator")  # Has prefix
```

**Check structural trigger:**
```python
from sage.triggers.structural import StructuralDetector
detector = StructuralDetector(get_config())
triggers = detector.analyze_message(msg, role="user")
```

**Combine triggers:**
```python
from sage.triggers.combiner import should_trigger
final = should_trigger(structural_trigger, linguistic_trigger)
if final:
    save_checkpoint(...)
```
