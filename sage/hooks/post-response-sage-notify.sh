#!/bin/bash
# Sage Notification Hook for Claude Code
#
# This script runs after each Claude Code response and displays
# any pending Sage notifications (checkpoint saves, knowledge saves, etc.).
#
# Install: sage hooks install
# Or manually: cp this file to ~/.claude/hooks/
#
# Security:
# - Uses jq for safe JSON parsing (no eval)
# - Notifications are already sanitized by Sage
# - File is removed after reading to prevent replay
#
# Requires: jq (JSON processor)

NOTIFY_FILE="$HOME/.sage/notifications.jsonl"

# Check if notification file exists
if [[ ! -f "$NOTIFY_FILE" ]]; then
    exit 0
fi

# Check if jq is available
if ! command -v jq &> /dev/null; then
    # Fallback: just show that notifications exist
    if [[ -s "$NOTIFY_FILE" ]]; then
        echo "⏺ Sage: Notifications pending (install jq to see details)"
    fi
    exit 0
fi

# Process each notification line
while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip empty lines
    [[ -z "$line" ]] && continue

    # Parse JSON safely with jq
    type=$(echo "$line" | jq -r '.type // "info"')
    msg=$(echo "$line" | jq -r '.msg // "Unknown notification"')

    # Display based on type
    case "$type" in
        success)
            echo "⏺ Sage: $msg"
            ;;
        error)
            echo "⏺ Sage Error: $msg"
            ;;
        warning)
            echo "⏺ Sage Warning: $msg"
            ;;
        *)
            echo "⏺ Sage: $msg"
            ;;
    esac
done < "$NOTIFY_FILE"

# Clear notifications after displaying
rm -f "$NOTIFY_FILE"
