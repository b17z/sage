#!/bin/bash
# PreCompact hook for Sage autosave
# Triggers checkpoint before context compaction
#
# Schema: input has `trigger` field ("auto" or "manual")
# Output uses `continue` (boolean), NOT `decision`

input=$(cat)
trigger=$(echo "$input" | jq -r '.trigger // "unknown"')

# Auto-compact (context overflow) - approve immediately to prevent deadlock
if [ "$trigger" = "auto" ]; then
    echo '{"continue": true}'
    exit 0
fi

# Manual compact (/compact command) - block for checkpoint
cat << 'EOF'
{
  "continue": false,
  "stopReason": "⚠️ CHECKPOINT BEFORE COMPACTING\n\nCall sage_autosave_check with trigger_event='precompact' to save:\n- core_question: What you've been researching\n- current_thesis: Your synthesized findings\n- confidence: How confident (0-1)\n- open_questions: What remains unanswered\n\nThen run /compact again."
}
EOF
