# Sage v2.0 Code Spec

**Purpose:** Implementation guide for Claude Code. Load this, not the full research spec.

**Full spec:** `sage-memory-framework-v2.5.md` (reference only when design rationale needed)

---

## Testing Requirements

**CRITICAL: Every feature implementation MUST include:**

1. **Unit tests** — Test individual functions in isolation
2. **Integration tests** — Test feature workflows end-to-end
3. **Edge case tests** — Empty inputs, malformed data, boundary conditions

**Current test count:** 91 tests
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
