# Storage Maintenance

Detailed documentation for Sage's storage maintenance features.

## Overview

Sage stores checkpoints and knowledge items on disk. Without maintenance, storage can grow unbounded, leading to:
- Slower startup times (loading large embedding stores)
- Disk space exhaustion
- Stale/irrelevant items polluting recall

Sage v3.1 introduces automatic maintenance to address these concerns.

## Configuration

All settings are configurable in `~/.sage/tuning.yaml` (user-level) or `<project>/.sage/tuning.yaml` (project-level):

```yaml
# Storage maintenance
checkpoint_max_age_days: 90      # Delete checkpoints older than N days
checkpoint_max_count: 200        # Cap to N most recent checkpoints
knowledge_max_age_days: 0        # Delete knowledge older than N days
maintenance_on_save: true        # Auto-run on save operations

# Caching
knowledge_cache_ttl_seconds: 45.0  # In-memory cache TTL
```

### Setting Maintenance to Zero

Setting `max_age_days` or `max_count` to `0` disables that pruning dimension:

```yaml
checkpoint_max_age_days: 0   # Never prune by age
checkpoint_max_count: 0      # Never prune by count (unlimited)
```

## Checkpoint Maintenance

### How It Works

When a checkpoint is saved (and `maintenance_on_save=true`):

1. **Age pruning** — Delete checkpoints with mtime older than `max_age_days`
2. **Count capping** — If remaining > `max_count`, delete oldest until under cap
3. **Embedding cleanup** — Remove orphaned embeddings for deleted checkpoints

### File-Based Age Detection

Checkpoint age is determined by file modification time (`mtime`), not internal metadata. This ensures:
- Consistent behavior regardless of checkpoint format
- No need to parse each file to determine age
- Accurate timing even if file was manually copied

### Embedding Cleanup

When a checkpoint is deleted, its embedding vector is also removed from the embedding store. This prevents:
- Orphaned embeddings consuming memory
- Stale embeddings affecting similarity searches
- Embedding store growth without bound

### Project Scoping

Checkpoint maintenance respects project boundaries:

```
~/.sage/checkpoints/          # Global checkpoints
my-project/.sage/checkpoints/ # Project-local checkpoints
```

Each directory is maintained independently.

## Knowledge Maintenance

### How It Works

When knowledge is added (and `maintenance_on_save=true`):

1. **Age pruning** — Delete knowledge items with `metadata.added` date older than `max_age_days`
2. **Content file cleanup** — Remove the `.md` content file
3. **Embedding cleanup** — Remove the item's embedding vector
4. **Index update** — Save updated index (invalidates cache)

### Why No Count Cap?

Knowledge items are explicitly added by users and represent intentional decisions about what to remember. Unlike checkpoints (auto-created during research), knowledge should only be removed through:
- Age-based pruning (`knowledge_max_age_days`)
- Manual removal (`sage_remove_knowledge`)
- Deprecation (`sage_deprecate_knowledge`)
- Archival (`sage_archive_knowledge`)

### Date-Based vs File-Based

Knowledge age uses the `metadata.added` field, not file mtime:

```yaml
# In knowledge index
items:
  - id: my-knowledge
    keywords: [keyword1, keyword2]
    metadata:
      added: '2026-01-15'  # This date is used for pruning
```

This allows knowledge to be copied/migrated without resetting its age.

## Caching

### Knowledge Index Cache

The knowledge index (`~/.sage/knowledge/index.yaml`) is cached in memory:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  load_index()   │────▶│  Check cache     │────▶│  Return     │
│                 │     │  TTL + mtime     │     │  cached     │
└─────────────────┘     └────────┬─────────┘     └─────────────┘
                                 │ miss
                                 ▼
                        ┌──────────────────┐     ┌─────────────┐
                        │  Read from disk  │────▶│  Update     │
                        │                  │     │  cache      │
                        └──────────────────┘     └─────────────┘
```

### Cache Validity

The cache is considered valid if **both** conditions are met:
1. **TTL not expired** — `time.time() - loaded_at < ttl_seconds`
2. **mtime unchanged** — File hasn't been modified externally

This dual-check ensures:
- Fast reads during normal operation (TTL check)
- Correct behavior after external edits (mtime check)

### Cache Invalidation

The cache is explicitly invalidated after:
- `save_index()` — After writing new index
- `add_knowledge()` — After adding item
- `remove_knowledge()` — After removing item
- `update_knowledge()` — After updating item

### Thread Safety

Cache operations use a lock to ensure thread safety:

```python
_index_cache_lock = threading.Lock()

def _get_cached_index() -> list[KnowledgeItem] | None:
    with _index_cache_lock:
        if _index_cache.is_valid(ttl_seconds):
            return list(_index_cache.items)  # Return copy
    return None
```

## Atomic Writes

All maintenance operations use atomic writes to prevent corruption:

```
┌─────────────────┐
│  Write to       │
│  temp file      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Set            │
│  permissions    │
│  (0o600)        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Rename to      │
│  final path     │
│  (atomic)       │
└─────────────────┘
```

This pattern ensures:
- **No partial writes** — File is complete or doesn't exist
- **Crash safety** — Power loss during write leaves old file intact
- **Permission safety** — New file has correct permissions from start

## Troubleshooting

### Checkpoints Not Being Pruned

1. Check `maintenance_on_save` is `true`:
   ```bash
   sage config list | grep maintenance
   ```

2. Check `max_age_days` and `max_count` aren't both `0`:
   ```bash
   sage config list | grep checkpoint_max
   ```

3. Verify file mtimes are as expected:
   ```bash
   ls -la ~/.sage/checkpoints/
   ```

### Knowledge Cache Seems Stale

1. Verify TTL setting:
   ```bash
   sage config list | grep cache_ttl
   ```

2. Check if file was modified externally:
   ```bash
   stat ~/.sage/knowledge/index.yaml
   ```

3. Force reload by calling any write operation, or restart the MCP server.

### Disk Space Still Growing

1. Check embedding store size:
   ```bash
   du -sh ~/.sage/*.npz
   ```

2. Orphaned embeddings may exist from before maintenance was added. Rebuild:
   ```bash
   sage admin rebuild-embeddings
   ```

## Performance Considerations

### Maintenance Overhead

Maintenance runs synchronously during save operations. Typical overhead:
- **< 10ms** for age pruning (stat calls only)
- **< 50ms** for count capping (sort + delete)
- **< 100ms** for embedding cleanup (numpy array modification)

### Cache Hit Rate

With default 45-second TTL, expect high cache hit rates during active sessions:
- **90%+** hit rate during research sessions
- **0%** hit rate on cold start (expected)

### Memory Usage

Knowledge index cache stores all items in memory. For large knowledge bases (500+ items), consider:
- Reducing `knowledge_cache_ttl_seconds` if memory-constrained
- Using `knowledge_max_age_days` to bound total items

## API Reference

### Checkpoint Maintenance

```python
from sage.checkpoint import run_checkpoint_maintenance, MaintenanceResult

result: MaintenanceResult = run_checkpoint_maintenance(
    project_path=None,      # Optional project path
    max_age_days=None,      # Override config (default: from config)
    max_count=None,         # Override config (default: from config)
)

# Result fields
result.pruned_by_age      # int: Count deleted for age
result.pruned_by_cap      # int: Count deleted for cap
result.total_remaining    # int: Count after maintenance
```

### Knowledge Maintenance

```python
from sage.knowledge import run_knowledge_maintenance, KnowledgeMaintenanceResult

result: KnowledgeMaintenanceResult = run_knowledge_maintenance(
    max_age_days=None,      # Override config (default: from config)
)

# Result fields
result.pruned_by_age      # int: Count deleted for age
result.total_remaining    # int: Count after maintenance
```

### Cache Control

```python
from sage.knowledge import _invalidate_index_cache

# Force cache invalidation (rarely needed)
_invalidate_index_cache()
```
