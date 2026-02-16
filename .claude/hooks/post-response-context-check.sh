#!/bin/bash
# Post-response hook that checks context usage and suggests checkpoint when high
#
# Reads the last entry from transcript JSONL to get actual token usage.
# If above threshold, blocks stop and instructs Claude to checkpoint first.
# Uses a marker file to prevent repeated firing after checkpoint.

THRESHOLD_PERCENT=${SAGE_CONTEXT_THRESHOLD:-70}  # Default: save at 70% (before autocompact at ~77%)
CONTEXT_WINDOW_SIZE=${SAGE_CONTEXT_WINDOW:-200000}  # Claude's context window
COOLDOWN_SECONDS=${SAGE_CONTEXT_COOLDOWN:-300}  # 5 min cooldown to prevent re-triggering

# Debug logging
DEBUG_LOG="${HOME}/.sage/logs/context-hook.log"
mkdir -p "$(dirname "$DEBUG_LOG")"
debug() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$DEBUG_LOG"
}

# Read hook input from stdin
input=$(cat)
debug "=== Hook invoked ==="

# Check hook_event_name - only process Stop events, skip others
hook_event=$(echo "$input" | jq -r '.hook_event_name // empty')
debug "hook_event: $hook_event"
if [ -n "$hook_event" ] && [ "$hook_event" != "Stop" ]; then
    # Not a Stop event - approve and exit
    debug "Skipping non-Stop event"
    echo '{"decision": "approve"}'
    exit 0
fi

# Extract session info from input
session_id=$(echo "$input" | jq -r '.session_id // empty')
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')

# Check for recent checkpoint marker (cooldown)
# Use ~/.sage/cooldown/ instead of /tmp for security (predictable /tmp paths risk symlink attacks)
cooldown_dir="${HOME}/.sage/cooldown"
mkdir -p "$cooldown_dir"
marker_file="${cooldown_dir}/context_threshold"
if [ -f "$marker_file" ]; then
    marker_time=$(cat "$marker_file")
    current_time=$(date +%s)
    elapsed=$((current_time - marker_time))
    debug "Cooldown check: elapsed=${elapsed}s, threshold=${COOLDOWN_SECONDS}s"
    if [ "$elapsed" -lt "$COOLDOWN_SECONDS" ]; then
        # Still in cooldown, approve
        debug "DECISION: approve (cooldown active)"
        echo '{"decision": "approve"}'
        exit 0
    fi
fi

# Default to approve if we can't read transcript
debug "transcript_path: $transcript_path"
if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
    debug "DECISION: approve (no transcript)"
    echo '{"decision": "approve"}'
    exit 0
fi

# Get usage from the last entry that has usage data
# User messages don't have usage, so we search backwards
# Each JSONL line is one complete JSON object
# Note: tail -r is macOS reverse, use awk to reverse on Linux
usage=""
while IFS= read -r line; do
    candidate=$(echo "$line" | jq -r '.message.usage // .usage // empty' 2>/dev/null)
    if [ -n "$candidate" ] && [ "$candidate" != "null" ] && [ "$candidate" != "" ]; then
        usage="$candidate"
        break
    fi
done < <(tail -20 "$transcript_path" | tail -r 2>/dev/null || tail -20 "$transcript_path" | awk '{a[NR]=$0} END{for(i=NR;i>=1;i--)print a[i]}')

if [ -z "$usage" ] || [ "$usage" = "null" ]; then
    # No usage data in recent entries, approve
    debug "DECISION: approve (no usage data in last 20 entries)"
    echo '{"decision": "approve"}'
    exit 0
fi

# Extract token counts from usage
current_input=$(echo "$usage" | jq -r '.input_tokens // 0')
current_output=$(echo "$usage" | jq -r '.output_tokens // 0')
cache_read=$(echo "$usage" | jq -r '.cache_read_input_tokens // 0')
cache_creation=$(echo "$usage" | jq -r '.cache_creation_input_tokens // 0')

debug "Token counts: input=$current_input, output=$current_output, cache_read=$cache_read, cache_creation=$cache_creation"

# Calculate total context usage
# input_tokens + cache_read = actual context consumed (cache_creation is subset of input)
total_tokens=$((current_input + cache_read + cache_creation))

# Calculate percentage
percent=$((total_tokens * 100 / CONTEXT_WINDOW_SIZE))
debug "Calculation: total=$total_tokens, window=$CONTEXT_WINDOW_SIZE, percent=$percent%, threshold=$THRESHOLD_PERCENT%"

# If above threshold, block and instruct checkpoint
if [ "$percent" -ge "$THRESHOLD_PERCENT" ]; then
    # Create marker file to start cooldown (prevents repeated blocking)
    date +%s > "$marker_file"
    debug "DECISION: block (${percent}% >= ${THRESHOLD_PERCENT}%)"
    cat << EOF
{
  "decision": "block",
  "reason": "Context at ${percent}% (${total_tokens}/${CONTEXT_WINDOW_SIZE} tokens). Call sage_autosave_check with trigger_event='context_threshold' to checkpoint before stopping."
}
EOF
else
    debug "DECISION: approve (${percent}% < ${THRESHOLD_PERCENT}%)"
    echo '{"decision": "approve"}'
fi
