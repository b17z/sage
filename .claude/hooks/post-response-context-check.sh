#!/bin/bash
# Post-response hook that checks context usage and suggests checkpoint when high
#
# Reads the last entry from transcript JSONL to get actual token usage.
# If above threshold, blocks stop and instructs Claude to checkpoint first.
# Uses a marker file to prevent repeated firing after checkpoint.

THRESHOLD_PERCENT=${SAGE_CONTEXT_THRESHOLD:-70}  # Default: save at 70% (before autocompact buffer)
CONTEXT_WINDOW_SIZE=${SAGE_CONTEXT_WINDOW:-200000}  # Claude's context window
COOLDOWN_SECONDS=${SAGE_CONTEXT_COOLDOWN:-60}  # 60 second rate limit after checkpoint

# Read hook input from stdin
input=$(cat)

# Extract session info from input
session_id=$(echo "$input" | jq -r '.session_id // empty')
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')

# Check for recent checkpoint marker (cooldown)
# Use ~/.sage/cooldown/ instead of /tmp for security (predictable /tmp paths risk symlink attacks)
cooldown_dir="${HOME}/.sage/cooldown"
mkdir -p "$cooldown_dir"
marker_file="${cooldown_dir}/checkpoint_${session_id}"
if [ -f "$marker_file" ]; then
    marker_time=$(cat "$marker_file")
    current_time=$(date +%s)
    elapsed=$((current_time - marker_time))
    if [ "$elapsed" -lt "$COOLDOWN_SECONDS" ]; then
        # Still in cooldown, approve
        echo '{"decision": "approve"}'
        exit 0
    fi
fi

# Default to approve if we can't read transcript
if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
    echo '{"decision": "approve"}'
    exit 0
fi

# Get usage from the last line of transcript
# Usage can be at .message.usage or .usage depending on message type
last_line=$(tail -1 "$transcript_path")
usage=$(echo "$last_line" | jq -r '.message.usage // .usage // empty')

if [ -z "$usage" ] || [ "$usage" = "null" ]; then
    # No usage data, approve
    echo '{"decision": "approve"}'
    exit 0
fi

# Extract token counts from usage
current_input=$(echo "$usage" | jq -r '.input_tokens // 0')
current_output=$(echo "$usage" | jq -r '.output_tokens // 0')
cache_read=$(echo "$usage" | jq -r '.cache_read_input_tokens // 0')
cache_creation=$(echo "$usage" | jq -r '.cache_creation_input_tokens // 0')

# Calculate total context usage
# input_tokens + cache_read = actual context consumed (cache_creation is subset of input)
total_tokens=$((current_input + cache_read + cache_creation))

# Calculate percentage
percent=$((total_tokens * 100 / CONTEXT_WINDOW_SIZE))

# If above threshold, block and instruct checkpoint
if [ "$percent" -ge "$THRESHOLD_PERCENT" ]; then
    # Create marker file to start cooldown (prevents repeated blocking)
    date +%s > "$marker_file"
    cat << EOF
{
  "decision": "block",
  "reason": "Context at ${percent}% (${total_tokens}/${CONTEXT_WINDOW_SIZE} tokens). Call sage_autosave_check with trigger_event='context_threshold' to checkpoint before stopping."
}
EOF
else
    echo '{"decision": "approve"}'
fi
