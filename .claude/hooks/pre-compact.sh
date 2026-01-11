#!/bin/bash
# PreCompact hook for Sage autosave
# Triggers checkpoint before context compaction

# Output JSON that blocks compaction until checkpoint is done
# PreCompact hooks only accept: approve, block (not SUGGEST)
cat << 'EOF'
{
  "decision": "block",
  "reason": "⚠️ CONTEXT COMPACTING - CHECKPOINT REQUIRED\n\nYou MUST call sage_autosave_check NOW before context is lost.\nUse trigger_event='precompact' and capture:\n- core_question: What you've been researching\n- current_thesis: Your synthesized findings\n- confidence: How confident you are\n- open_questions: What remains unanswered\n\nAfter checkpointing, run /compact again."
}
EOF
