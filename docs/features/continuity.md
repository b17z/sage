# Session Continuity

Automatic context restoration after Claude Code compaction events.

## The Problem

Claude Code compacts context when it gets too long. After compaction:
- Working memory is lost
- Research context disappears
- You have to re-explain what you were doing

## The Solution

Sage's watcher daemon monitors for compaction and automatically injects context on the next tool call.

```
┌─────────────────────────────────────────────────────────────┐
│  Research in progress...                                     │
│  "I'm investigating how auth works"                          │
└─────────────────────────────────────────────────────────────┘
                            │
                   70% context reached
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Checkpoint saved automatically                              │
│  thesis: "JWT tokens with refresh rotation..."              │
│  files_explored: [auth.py, middleware.py, ...]              │
└─────────────────────────────────────────────────────────────┘
                            │
                   Context compacts
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Watcher detects isCompactSummary: true                     │
│  Writes continuity marker                                    │
└─────────────────────────────────────────────────────────────┘
                            │
                   Next Sage tool call
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Context injected automatically:                             │
│                                                              │
│  "═══ SESSION CONTINUITY ═══                                │
│                                                              │
│   **Claude Code Compaction Summary:**                       │
│   User was researching JWT authentication...                │
│                                                              │
│   **Last Checkpoint:**                                      │
│   Thesis: JWT tokens with refresh rotation...               │
│   Files explored: auth.py, middleware.py, ...               │
│   ═══════════════════════════"                              │
└─────────────────────────────────────────────────────────────┘
```

## How It Works

### 1. Checkpoint at 70% Context

The context-check hook saves a checkpoint when usage hits 70%:

```bash
# ~/.claude/hooks/post-response-context-check.sh
# Triggers: sage_autosave_check(trigger_event="context_threshold")
```

### 2. Watcher Daemon

Monitors Claude Code transcripts for compaction:

```bash
sage watcher start    # Start watching
sage watcher stop     # Stop watching
sage watcher status   # Check status
```

The watcher:
- Polls transcript JSONL files
- Detects `{"isCompactSummary": true}` messages
- Extracts the compaction summary
- Writes a continuity marker

### 3. Automatic Injection

On the next Sage tool call (`sage_health()`, etc.):
1. Check for continuity marker
2. Load referenced checkpoint
3. Prepend context to response
4. Clear marker (one-time injection)

## Usage

### Starting the Watcher

```bash
# Manual start
sage watcher start

# Auto-start on MCP init (opt-in)
# In ~/.sage/tuning.yaml:
watcher_auto_start: true
```

### Checking Status

```bash
sage watcher status
```

Shows:
- Running/stopped state
- PID and log location
- Recent log entries

### MCP Tools

```python
# Check continuity and inject if pending
sage_continuity_status()

# Health check (also injects)
sage_health()
```

## Configuration

```yaml
# ~/.sage/tuning.yaml

continuity_enabled: true    # Enable context injection (default)
watcher_auto_start: false   # Auto-start on MCP init (opt-in)
```

## Continuity Marker

When compaction is detected, watcher writes:

```json
// ~/.sage/continuity.json
{
  "checkpoint_id": "2026-02-13T12-00-00_jwt-research",
  "marked_at": "2026-02-13T12:05:00Z",
  "reason": "compaction_detected",
  "summary": "User was researching JWT authentication..."
}
```

### Manual Marking

For testing:

```bash
sage continuity mark --reason "testing"
sage continuity status
sage continuity clear
```

## Learning Perspective

### Why Continuity Matters for Learning

The compaction break can disrupt your learning flow. Without continuity:

```
Before: "I was starting to understand how the refresh flow works..."
After:  "I have no context. Let me re-read everything."
```

With continuity, you get:
```
After:  "Picking up where you left off:
         - You were researching JWT refresh tokens
         - You explored auth.py and middleware.py
         - Your working thesis was..."
```

This preserves not just *what* you were doing, but *where you were in the learning process*.

### The Checkpoint Is Your Learning State

The injected checkpoint includes:
- `thesis` — Your current understanding
- `open_questions` — What you still didn't get
- `files_explored` — What code you'd already read
- `reasoning_trace` — How you were thinking about it

This is more than a summary — it's a snapshot of your learning state.

## Security

- **Daemon runs as user's process** — no privilege escalation
- **PID/log files have 0o600 permissions** — only owner can read
- **Path validation** — symlinks outside expected directories skipped
- **No code execution** — JSON parsed safely
- **Line length limit** — 10MB max to prevent memory exhaustion

## Plugin Integration

The watcher uses plugins for extensibility:

| Plugin | Purpose |
|--------|---------|
| `session` | Track session boundaries |
| `recovery` | Create recovery checkpoints |
| `checkpoint-queue` | Queue checkpoints for injection |

See [Plugin Architecture](./plugins.md) for details.

## Troubleshooting

### Watcher not detecting compaction

```bash
sage watcher status
# Check log for errors

# Verify transcript location
ls ~/.claude/projects/
```

### Context not injecting

```bash
sage continuity status
# Check if marker exists

# Clear and retry
sage continuity clear --force
```

### Watcher won't start

```bash
# Check if already running
sage watcher status

# Force stop and restart
sage watcher stop
sage watcher start
```

## Related

- [Checkpointing](./checkpointing.md) — Saves the research state
- [Plugin Architecture](./plugins.md) — Watcher extensibility
- [Configuration](./configuration.md) — Tuning options
