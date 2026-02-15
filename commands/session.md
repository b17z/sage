---
description: Check session continuity and inject pending context
---

# /session

Check session status and manage context continuity.

## Usage

```
/session [status|inject|health]
```

## Subcommands

### Check status
```
/session status
```
Shows:
- Whether context was restored from a previous session
- Pending checkpoints to inject
- Watcher daemon status

### Inject context
```
/session inject
```
Manually inject any pending context from:
- Compaction recovery checkpoints
- Queued checkpoints from watcher
- Core files marked for auto-injection

### Health check
```
/session health
```
Full diagnostic of Sage systems:
- Configuration status
- Embedding model availability
- Checkpoint and knowledge counts
- File permissions
- Pending tasks

## Implementation

Map to MCP tools:
- `status` → `sage_continuity_status()`
- `inject` → `sage_continuity_status()` (triggers injection)
- `health` → `sage_health()`

## When to Use

### Session Start
At the beginning of a new session, run:
```
/session status
```
This automatically injects any pending context from:
- Previous session's recovery checkpoint
- Compaction-triggered checkpoints
- Manual queue

### After Compaction
If you notice context was compacted (conversation shortened), run:
```
/session inject
```
This restores checkpointed context.

### Debugging
If Sage isn't working as expected:
```
/session health
```
Shows what's working and what isn't.

## Output Format

### Status
```markdown
## Session Status

**Continuity:** Context restored from checkpoint `2026-02-14_auth-research`
**Watcher:** Running (PID 12345)
**Pending:** No checkpoints queued

Last checkpoint: 2 hours ago
Knowledge items: 15 active
```

### Health
```markdown
## Sage Health

| Component | Status |
|-----------|--------|
| Config | OK |
| Embeddings | OK (bge-large-en-v1.5) |
| Checkpoints | 142 files |
| Knowledge | 15 items |
| Watcher | Running |
| Code Index | Stale (3 files changed) |
```
