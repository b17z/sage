# Git Versioning (v4.0)

Optionally commit checkpoint and knowledge saves to git. Every save creates a commit, giving you version history for your research.

## Overview

When enabled, Sage automatically commits changes to `.sage/`:

```bash
$ git log --oneline
a1b2c3d sage: checkpoint jwt-research-final
f4e5d6c sage: knowledge auth-patterns
7g8h9i0 sage: failure jwt-localstorage
```

This gives you:
- **History** — See how research evolved
- **Recovery** — Restore previous versions
- **Collaboration** — Share `.sage/` via git

## Enabling Git Versioning

Git versioning is **off by default**. Enable it in your config:

```yaml
# .sage/tuning.yaml
git_versioning_enabled: true
```

Or via MCP:

```python
sage_set_config("git_versioning_enabled", "true")
sage_reload_config()
```

## Commit Format

Commits follow a consistent format:

```
sage: {type} {item_id}
```

Examples:
```
sage: checkpoint jwt-research-phase2
sage: knowledge usdc-compliance
sage: failure sqlite-multithread
```

## What Gets Committed

| Operation | Commits |
|-----------|---------|
| `sage_save_checkpoint()` | Yes |
| `sage_save_knowledge()` | Yes |
| `sage_record_failure()` | Yes |
| `sage_update_knowledge()` | Yes |
| `sage_remove_knowledge()` | No (deletions not committed) |

## Requirements

- Project must be a git repository
- `.sage/` directory must exist
- Git must be installed and accessible
- `.sage/` must be tracked by git (not in `.gitignore`)

### Default Setup

By default, Sage projects track `.sage/` with these exceptions in `.gitignore`:

```gitignore
# Sage - project .sage/ is shareable
.sage/local/              # Local overrides (not shared)
.sage/codebase/lancedb/   # Large generated index files
```

This means checkpoints, knowledge, failures, and system folder files are all versioned.

## Implementation

### Commit Function

```python
def commit_sage_change(
    file_path: Path,
    change_type: str,
    item_id: str,
    repo_path: Path | None = None,
) -> bool:
    """Commit a Sage file change to git."""
```

See [`sage/git.py`](../../sage/git.py) for the full implementation.

### History Function

```python
def get_sage_history(
    repo_path: Path | None = None,
    limit: int = 20,
) -> list[SageCommit]:
    """Get recent Sage commits."""
```

Returns:
```python
@dataclass(frozen=True)
class SageCommit:
    sha: str           # Commit SHA
    message: str       # Full commit message
    timestamp: str     # ISO timestamp
    change_type: str   # "checkpoint", "knowledge", "failure"
    item_id: str       # Item identifier
```

## Behavior Notes

1. **No auto-push** — Commits are local only. Push manually.
2. **No-verify** — Uses `--no-verify` to skip pre-commit hooks
3. **Graceful failure** — If git fails, the save still succeeds
4. **Local only** — Does not affect remote or other branches

## Viewing History

```bash
# All Sage commits
git log --oneline --grep="^sage:"

# Just checkpoints
git log --oneline --grep="^sage: checkpoint"

# Specific item
git log --oneline --grep="jwt-research"

# With diff
git show HEAD --stat
```

## Recovery

Restore a previous version:

```bash
# See history
git log --oneline .sage/checkpoints/

# Restore specific file
git checkout abc123 -- .sage/checkpoints/2026-02-15_jwt-research.md

# Or restore all Sage state
git checkout abc123 -- .sage/
```

## Security Considerations

- **Secrets** — `.sage/` may contain research about sensitive topics
- **Git history** — Once committed, removing is difficult
- **Team repos** — Consider if `.sage/` should be in `.gitignore`

Recommended `.gitignore` for team repos:
```gitignore
# Keep project Sage state
.sage/

# But ignore local overrides
.sage/local/
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `git_versioning_enabled` | `false` | Enable git commits for saves |

## Best Practices

1. **Enable for solo projects** — Full history is valuable
2. **Consider for teams** — Discuss if `.sage/` should be shared
3. **Review before push** — Check what's being committed
4. **Use branches** — Experiment on branches, merge good research
