#!/bin/bash
# Sage pre-compact hook
# Logs compaction events to active Sage skill session

ACTIVE_SKILL=$(cat ~/.sage/.active_skill 2>/dev/null)
if [ -n "$ACTIVE_SKILL" ]; then
    SESSION_NOTES="$HOME/.sage/skills/$ACTIVE_SKILL/SESSION_NOTES.md"
    if [ -f "$SESSION_NOTES" ]; then
        echo "" >> "$SESSION_NOTES"
        echo "---" >> "$SESSION_NOTES"
        echo "" >> "$SESSION_NOTES"
        echo "## $(date '+%Y-%m-%d %H:%M:%S %Z') (Auto-compacted)" >> "$SESSION_NOTES"
        echo "" >> "$SESSION_NOTES"
        echo "*Context was auto-compacted. Review conversation summary above.*" >> "$SESSION_NOTES"
    fi
fi
