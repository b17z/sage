#!/bin/bash
# Post-response hook that checks context usage and suggests checkpoint when high
#
# Reads transcript to estimate context usage. If above threshold, suggests
# calling sage_autosave_check to save before context gets too full.

THRESHOLD_PERCENT=${SAGE_CONTEXT_THRESHOLD:-80}  # Default: save at 80% usage

# Read hook input from stdin
input=$(cat)

# Extract transcript path and context window info
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')
context_window_size=$(echo "$input" | jq -r '.context_window.context_window_size // 200000')
current_input=$(echo "$input" | jq -r '.context_window.current_usage.input_tokens // 0')
current_output=$(echo "$input" | jq -r '.context_window.current_usage.output_tokens // 0')
cache_read=$(echo "$input" | jq -r '.context_window.current_usage.cache_read_input_tokens // 0')

# Calculate current usage (input + output + cache_read all count toward context)
total_tokens=$((current_input + current_output + cache_read))

# Calculate percentage
if [ "$context_window_size" -gt 0 ]; then
    percent=$((total_tokens * 100 / context_window_size))
else
    percent=0
fi

# If above threshold, block and instruct checkpoint
if [ "$percent" -ge "$THRESHOLD_PERCENT" ]; then
    cat << EOF
{
  "decision": "block",
  "reason": "Context at ${percent}% (threshold: ${THRESHOLD_PERCENT}%). Call sage_autosave_check with trigger_event='context_threshold' to checkpoint before stopping."
}
EOF
else
    # Below threshold, allow stop
    echo '{"decision": "approve"}'
fi
