# Configuration

Sage uses a layered configuration system with sensible defaults that can be overridden at project or user level.

## Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| `config.yaml` | `~/.sage/` | API key, model settings (secrets) |
| `tuning.yaml` | `~/.sage/` or `<project>/.sage/` | Tunable thresholds |

## Config Cascade

Resolution order (highest priority first):
1. **Project-local** `.sage/tuning.yaml`
2. **User-level** `~/.sage/tuning.yaml`
3. **Built-in defaults**

This allows project-specific settings while maintaining user defaults.

## Tuning Parameters

### Retrieval Thresholds

```yaml
# ~/.sage/tuning.yaml

# Knowledge recall - how similar must content be to surface?
recall_threshold: 0.70       # Lower = more results, more noise
                             # Higher = fewer results, more precision

# Checkpoint deduplication - how similar before skipping save?
dedup_threshold: 0.90        # Lower = more aggressive dedup
                             # Higher = allow similar checkpoints

# Hybrid scoring weights
embedding_weight: 0.70       # Semantic similarity weight
keyword_weight: 0.30         # Keyword match weight
                             # Must sum to 1.0
```

### Trigger Detection

```yaml
# Structural detection thresholds
topic_drift_threshold: 0.50  # Similarity below this = topic shift
convergence_question_drop: 0.20  # Question ratio drop = synthesis

# Combined score threshold for triggering checkpoints
trigger_threshold: 0.60      # 70/30 weighted score must exceed this
```

### Depth Requirements

```yaml
# Minimum conversation depth before allowing checkpoints
depth_min_messages: 8        # Conversations shorter than this skip checkpoint
depth_min_tokens: 2000       # Token counts below this skip checkpoint

# Exempt triggers (bypass depth check):
# - manual, precompact, context_threshold, research_start
```

### Autosave Thresholds

```yaml
# Minimum confidence required for each trigger type
autosave_research_start: 0.0      # Always save
autosave_web_search_complete: 0.3
autosave_synthesis: 0.5
autosave_topic_shift: 0.3
autosave_user_validated: 0.4
autosave_constraint_discovered: 0.3
autosave_branch_point: 0.4
autosave_precompact: 0.0          # Always save
autosave_context_threshold: 0.0   # Always save
autosave_manual: 0.0              # Always save
```

### Embedding Models

```yaml
# Prose model (knowledge, checkpoints)
embedding_model: BAAI/bge-large-en-v1.5

# Code model (code indexing, search)
code_embedding_model: codesage/codesage-large
```

See [Embeddings](./embeddings.md) for available models.

### Session Continuity

```yaml
continuity_enabled: true     # Enable context injection after compaction
watcher_auto_start: false    # Auto-start watcher on MCP init (opt-in)
```

### Recovery Checkpoints

```yaml
recovery_enabled: true           # Generate recovery checkpoints on compaction
recovery_use_claude: false       # Use headless Claude for extraction (opt-in)
recovery_salience_threshold: 0.5 # Min salience to save observation
```

### Storage Maintenance

```yaml
# Checkpoint pruning
checkpoint_max_age_days: 90  # Delete older than N days (0 = never)
checkpoint_max_count: 200    # Keep only N most recent (0 = unlimited)
maintenance_on_save: true    # Auto-run on save operations

# Knowledge pruning
knowledge_max_age_days: 0    # Delete older than N days (0 = never)

# Caching
knowledge_cache_ttl_seconds: 45.0  # Index cache TTL
```

### Async Settings

```yaml
async_enabled: false         # Sync by default
notify_success: true         # Show success notifications
notify_errors: true          # Show error notifications
worker_timeout: 5.0          # Graceful shutdown timeout (seconds)
```

### Logging

```yaml
logging_enabled: true        # Enable structured JSON logging
log_level: INFO              # DEBUG, INFO, WARNING, ERROR
```

### Poll Agent

```yaml
poll_agent_type: general-purpose  # Agent type for task polling
poll_agent_model: haiku           # Model for polling agent
```

## CLI Commands

```bash
# Show all settings
sage config list

# Set user-level value
sage config set recall_threshold 0.65

# Set project-level value
sage config set recall_threshold 0.75 --project

# Reset to defaults
sage config reset
sage config reset --project
```

## MCP Tools

```python
# Get current config
sage_get_config()

# Set a value
sage_set_config("recall_threshold", "0.65")
sage_set_config("recall_threshold", "0.75", project_level=True)

# Reload after changes
sage_reload_config()

# Debug retrieval scoring
sage_debug_query("authentication patterns")
```

## Debugging Retrieval

Use `sage_debug_query()` to understand why items are/aren't being recalled:

```python
sage_debug_query("authentication")

# Returns:
# {
#   "query": "authentication",
#   "matches": [
#     {"id": "jwt-expiry", "score": 0.82, "threshold": 0.70, "status": "matched"},
#     {"id": "old-auth", "score": 0.68, "threshold": 0.70, "status": "near-miss"}
#   ],
#   "near_misses": [...],
#   "config": {"recall_threshold": 0.70, "embedding_weight": 0.70, ...}
# }
```

If items aren't being recalled:
1. Check their score vs threshold
2. Lower `recall_threshold` to include them
3. Or add better keywords to the item

## Storage Layout

```
~/.sage/                      # User-level (NEVER in git repos)
├── config.yaml               # API key, model preferences (secrets!)
├── tuning.yaml               # User threshold defaults
├── checkpoints/              # Global checkpoints
├── knowledge/                # Global knowledge
├── embeddings/               # Embedding caches
└── logs/                     # Structured logs

<project>/.sage/              # Project-level (shareable via git)
├── tuning.yaml               # Project-specific thresholds
├── checkpoints/              # Project checkpoints
├── knowledge/                # Project knowledge
├── codebase/                 # Code index
└── local/                    # GITIGNORED - project-local overrides
```

## Security Notes

- `config.yaml` may contain API keys — **never commit**
- `tuning.yaml` is safe to commit (no secrets)
- All config files use `chmod 0o600` (owner-only)
- YAML uses `safe_load()` only (no code execution)

## Default Values

All defaults are defined in `SageConfig`:

**Source:** [`sage/config.py:137-203`](../../sage/config.py)

## Validation

SageConfig validates on initialization:

- Warns if weights don't sum to 1.0
- Warns if `checkpoint_max_count` is very low (<10)
- Clamps negative age values to 0

## Related

- [Embeddings](./embeddings.md) — Model configuration
- [Storage Maintenance](./maintenance.md) — Pruning configuration
- [Trigger Detection](./triggers.md) — Threshold tuning
