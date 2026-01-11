#!/bin/bash
# PreCompact hook for Sage autosave
# Triggers checkpoint before context compaction

# Output JSON that injects a checkpoint instruction into Claude's context
cat << 'EOF'
{
  "decision": "SUGGEST",
  "message": "⚠️ CONTEXT COMPACTING - CHECKPOINT REQUIRED\n\nYou MUST call sage_autosave_check NOW before context is lost.\nUse trigger_event='precompact' and capture:\n- core_question: What you've been researching\n- current_thesis: Your synthesized findings\n- confidence: How confident you are\n- open_questions: What remains unanswered\n\nThis is NOT optional. Checkpoint now, then continue."
}
EOF
