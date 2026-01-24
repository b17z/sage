# Session Continuity

Sage's session continuity feature prevents context loss when Claude Code's context window auto-compacts or when you start a new session.

## The Problem

When Claude Code's context window fills up (~70% capacity), it automatically compacts—summarizing the conversation to make room. This loses nuanced research findings, open questions, and your current thesis.

Similarly, starting a new session means starting from scratch, even if you were mid-research.

## The Solution

Sage captures context at critical moments and automatically injects it when you resume:

1. **Before compaction**: The 70% context hook saves a checkpoint
2. **After compaction**: The watcher daemon detects the compaction and writes a continuity marker
3. **Next session**: Any Sage tool call automatically injects the saved context

## How It Works

### Continuity Marker

When compaction is detected, Sage writes a marker file (`~/.sage/continuity.json`) containing:

```json
{
  "checkpoint_id": "2026-01-24_research-synthesis",
  "checkpoint_path": "/path/to/checkpoint.md",
  "compaction_summary": "Claude's summary of what was happening...",
  "marked_at": "2026-01-24T15:30:00Z",
  "reason": "post_compaction"
}
```

### Context Injection

On the next Sage tool call (any of `sage_health`, `sage_version`, `sage_list_checkpoints`, etc.), Sage:

1. Checks for a pending continuity marker
2. Loads the referenced checkpoint
3. Formats it for context injection
4. Prepends it to the tool response
5. Clears the marker (one-time injection)

### Proactive Recall

In addition to checkpoint continuity, Sage also injects **proactive recall**—knowledge items that match your current project context:

- Detects project from directory name, git remote, or package files
- Matches stored knowledge against project signals
- Injects relevant knowledge alongside continuity context

## Compaction Watcher (Opt-in)

The watcher daemon monitors Claude Code's transcript files for compaction events:

```bash
# Start the watcher (runs in background)
sage watcher start

# Check status
sage watcher status

# Stop the watcher
sage watcher stop
```

### How the Watcher Works

1. Finds the most recently modified transcript in `~/.claude/projects/`
2. Tails the JSONL file, watching for new entries
3. Detects `isCompactSummary: true` in the transcript
4. Extracts the compaction summary
5. Calls `mark_for_continuity()` to create the marker

### Log File

Watcher logs are written to `~/.sage/logs/watcher.log`:

```
[2026-01-24 15:30:00] Watching: /path/to/transcript.jsonl
[2026-01-24 16:45:00] Compaction detected! Summary length: 1234
[2026-01-24 16:45:00] Continuity marker written: /path/to/continuity.json
```

## Without the Watcher

Even without the watcher daemon, you still get continuity via:

1. **Pre-compact hook**: Saves checkpoint when you run `/compact`
2. **70% context hook**: Saves checkpoint at high context usage
3. **Manual checkpoints**: `sage_save_checkpoint` preserves state anytime

The watcher adds detection of *auto-compaction* (when Claude Code compacts automatically without you running `/compact`).

## MCP Tools

| Tool | Purpose |
|------|---------|
| `sage_health()` | Injects continuity + proactive recall (recommended on session start) |
| `sage_continuity_status()` | Check pending continuity, inject if present |

## CLI Commands

```bash
# Watcher management
sage watcher start    # Start daemon
sage watcher stop     # Stop daemon
sage watcher status   # Check if running

# Continuity status
sage continuity status  # Check for pending continuity
```

## Configuration

Continuity can be disabled via config:

```yaml
# In ~/.sage/tuning.yaml or .sage/tuning.yaml
continuity_enabled: false  # Default: true
```

## Security

- Marker file has restricted permissions (0o600)
- PID file has restricted permissions (0o600)
- Log file has restricted permissions (0o600)
- Paths are validated before use
- No arbitrary code execution from transcript content

## Troubleshooting

### Watcher not detecting compaction

1. Check watcher is running: `sage watcher status`
2. Check logs: `cat ~/.sage/logs/watcher.log`
3. Verify transcript exists: The watcher looks in `~/.claude/projects/*/` for `.jsonl` files

### Continuity not injecting

1. Check marker exists: `sage continuity status`
2. Ensure you're calling a Sage tool (context injects on first tool call)
3. Check if `continuity_enabled: false` in your config

### Windows support

The watcher daemon uses `fork()` which is not available on Windows. On Windows, use hooks-based continuity (pre-compact, 70% context) instead.
