# Sage Hooks

Sage uses Claude Code hooks to enable automatic checkpointing based on semantic triggers and context thresholds.

## Overview

Three hooks work together to preserve research context:

| Hook | Type | Triggers When |
|------|------|---------------|
| `post-response-context-check.sh` | Stop | Context exceeds 70% of window |
| `post-response-semantic-detector.sh` | Stop | Semantic patterns detected in output |
| `pre-compact.sh` | PreCompact | User runs `/compact` |

## Installation

### Automatic (recommended)

```bash
sage hooks install
```

This copies hook scripts to `~/.claude/hooks/` and updates `~/.claude/settings.json` automatically.

Other commands:
```bash
sage hooks status     # Check installation status
sage hooks uninstall  # Remove hooks
sage hooks install -f # Force overwrite existing hooks
```

### Manual

If you prefer manual installation:

```bash
mkdir -p ~/.claude/hooks
cp .claude/hooks/*.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh
```

Then add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "/path/to/hooks/post-response-context-check.sh" },
          { "type": "command", "command": "/path/to/hooks/post-response-semantic-detector.sh" }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "/path/to/hooks/pre-compact.sh" }
        ]
      }
    ]
  }
}
```

## Hook Details

### Context Check Hook

**File:** `post-response-context-check.sh`

**Purpose:** Triggers checkpoint when context window usage exceeds threshold (default 70%).

**How it works:**
1. Reads token usage from the last entry in transcript JSONL
2. Calculates percentage of 200k context window used
3. If above threshold, blocks stop and instructs Claude to checkpoint

**Configuration (environment variables):**

| Variable | Default | Description |
|----------|---------|-------------|
| `SAGE_CONTEXT_THRESHOLD` | `70` | Percentage threshold for checkpoint trigger |
| `SAGE_CONTEXT_WINDOW` | `200000` | Claude's context window size |
| `SAGE_CHECKPOINT_COOLDOWN` | `300` | Seconds before hook can fire again |

**Why 70%?** Claude Code's autocompact buffer is ~45k tokens (22.5%). Setting threshold to 70% gives ~15k token headroom before autocompact kicks in.

**Example output when triggered:**
```json
{
  "decision": "block",
  "reason": "Context at 74% (148000/200000 tokens). Call sage_autosave_check with trigger_event='context_threshold' to checkpoint before stopping."
}
```

### Semantic Detector Hook

**File:** `post-response-semantic-detector.sh`

**Purpose:** Detects semantic patterns in Claude's output that indicate checkpoint-worthy moments.

**Detected patterns (priority order):**

1. **topic_shift** (highest) - Context change, checkpoint before losing previous context
   - "moving on to", "let's turn to", "shifting gears", "changing topics"

2. **branch_point** - Decision point with multiple options
   - "we could either", "two approaches", "Option A/B", "alternatively"

3. **constraint_discovered** - Blocker or limitation found
   - "won't work because", "blocked by", "deal-breaker", "rules out"

4. **synthesis** (lowest) - Conclusion or recommendation
   - "in conclusion", "my take", "bottom line", "putting this together"

**Why priority order matters:** Synthesis phrases appear in most conclusions. Without priority, synthesis would always win when multiple patterns are present. The ordering ensures more actionable triggers (topic_shift, branch_point) take precedence.

**Meta-discussion ban list:**

The hook skips detection when the message discusses the hook system itself to prevent trigger loops:
```bash
(hook|checkpoint|trigger|pattern|detector|cooldown|sage_autosave).*(fire|detect|block|test)
```

**Cooldown mechanism:**

Each trigger type has an independent 5-minute cooldown using marker files:
```
~/.sage/cooldown/semantic_${session_id}_${trigger_type}
```

**Configuration:**

| Variable | Default | Description |
|----------|---------|-------------|
| `SAGE_SEMANTIC_COOLDOWN` | `300` | Seconds before same trigger type can fire again |

### Pre-Compact Hook

**File:** `pre-compact.sh`

**Purpose:** Triggers checkpoint before context compaction to preserve state.

**How it works:**
1. User runs `/compact`
2. Hook blocks compaction
3. Instructs Claude to checkpoint first
4. User can run `/compact` again after checkpointing

**Note:** This hook always blocks. Claude must checkpoint, then user re-runs `/compact`.

## Hook JSON Format

Stop hooks return JSON with these fields:

```json
{
  "decision": "approve" | "block",
  "reason": "Message shown to user and injected to Claude (when blocking)"
}
```

- `decision: "approve"` - Allow stop, no action
- `decision: "block"` - Prevent stop, inject reason as instruction to Claude

**Important:** Claude Code displays `decision: "block"` as "Stop hook error: [reason]" - this is cosmetic, not an actual error. It's the documented way to inject instructions.

## Testing Hooks

### Unit tests

Run the test suite:

```bash
./.claude/hooks/test_hooks.sh
```

### Manual testing

**Test context threshold:**
1. Have a long conversation (>140k tokens)
2. Check `/context` for usage
3. Try to stop - hook should block and request checkpoint

**Test semantic detector:**
1. Ask Claude a question that will produce synthesis ("What's your recommendation on X?")
2. Look for "Stop hook error: Synthesis detected..."
3. Claude should call `sage_autosave_check`

**Test pre-compact:**
1. Run `/compact`
2. Hook should block and request checkpoint
3. After checkpointing, run `/compact` again

## Troubleshooting

**Hook not firing:**
- Check hook is executable: `chmod +x ~/.claude/hooks/*.sh`
- Check settings.json has correct paths
- Check jq is installed: `which jq`

**Hook firing too often:**
- Cooldown may have expired (5 min default)
- Adjust `SAGE_SEMANTIC_COOLDOWN` or `SAGE_CHECKPOINT_COOLDOWN`

**False positives on meta-discussion:**
- The meta-ban list should catch most cases
- If you find new false positive patterns, add them to the ban list regex

**Hook causes errors:**
- Check transcript path exists: hook input includes `transcript_path`
- Check jq parsing: `echo '{"test": "value"}' | jq -r '.test'`
