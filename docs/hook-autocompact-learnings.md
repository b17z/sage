# Hook + Autocompact Learnings (Jan 2026)

## The Deadlock Bug

**Problem:** PreCompact hooks blocking autocompact caused session deadlock.

**Mechanism:**
1. Context hits ~80% threshold
2. Stop hook blocks, requesting checkpoint
3. Autocompact triggers (context overflow)
4. PreCompact hook blocks ALL compaction (bug!)
5. Deadlock - can't proceed, can't compact

**Root cause:**
- `pre-compact.sh` used wrong schema (`decision` vs `continue`)
- Blocked ALL compaction, including `trigger: "auto"` (context overflow)
- Fragile string match `*"compact"*` in Stop hook

## The Fix

### PreCompact Hook Schema

**Input:**
```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../session.jsonl",
  "hook_event_name": "PreCompact",
  "trigger": "auto" | "manual",
  "custom_instructions": ""
}
```

**Output:**
```json
{"continue": true}              // Allow compaction
{"continue": false, "stopReason": "..."}  // Block with message
```

**NOT** `{"decision": "approve/block"}` - that's Stop hook schema!

### Fixed pre-compact.sh

```bash
#!/bin/bash
input=$(cat)
trigger=$(echo "$input" | jq -r '.trigger // "unknown"')

# Auto-compact (context overflow) - approve to prevent deadlock
if [ "$trigger" = "auto" ]; then
    echo '{"continue": true}'
    exit 0
fi

# Manual compact (/compact) - block for checkpoint
echo '{"continue": false, "stopReason": "Checkpoint first..."}'
```

### Fixed Stop Hook

Replace fragile string match:
```bash
# BAD: if [[ "$input" == *"compact"* ]]; then

# GOOD: Check hook_event_name field
hook_event=$(echo "$input" | jq -r '.hook_event_name // empty')
if [ -n "$hook_event" ] && [ "$hook_event" != "Stop" ]; then
    echo '{"decision": "approve"}'
    exit 0
fi
```

## The Philosophical Question

> "Why use Sage if you can just block autocompact?"

**Blocking autocompact = expensive procrastination:**
1. Context grows unbounded
2. Hits 100% hard wall eventually
3. Burning $$$ on massive context window
4. Session ends = everything lost

**Sage checkpoints solve different problem:**
- Work ACROSS sessions (restore tomorrow)
- Semantic structure (thesis, confidence, sources, tensions)
- Selective preservation (key insights, not noise)
- Cheaper than maintaining 200K context forever

**Autocompact summary:**
- Lossy compression
- Works within single session
- Dies when terminal closes
- No semantic structure

## Testing the Hooks

```bash
# Test pre-compact with auto trigger (should approve)
echo '{"trigger": "auto"}' | .claude/hooks/pre-compact.sh
# Output: {"continue": true}

# Test pre-compact with manual trigger (should block)
echo '{"trigger": "manual"}' | .claude/hooks/pre-compact.sh
# Output: {"continue": false, "stopReason": "..."}

# Test Stop hook skips non-Stop events
echo '{"hook_event_name": "PreCompact"}' | .claude/hooks/post-response-context-check.sh
# Output: {"decision": "approve"}
```

## Files Modified

- `~/.claude/hooks/pre-compact.sh` (user-level)
- `~/.claude/hooks/post-response-context-check.sh` (user-level)
- `.claude/hooks/pre-compact.sh` (project-level)
- `.claude/hooks/post-response-context-check.sh` (project-level)
