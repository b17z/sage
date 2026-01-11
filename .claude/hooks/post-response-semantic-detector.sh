#!/bin/bash
# Semantic Detector Hook
#
# Monitors Claude's output for semantic triggers and injects checkpoint reminders.
# This makes semantic triggers hook-driven instead of relying on self-recognition.
#
# Detected triggers:
# - synthesis: "in conclusion", "putting this together", "this suggests"
# - branch_point: "we could either", "two approaches", "alternatively"
# - constraint_discovered: "can't", "won't work because", "limitation"

input=$(cat)

# Extract transcript path
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')

if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
    echo '{"decision": "APPROVE"}'
    exit 0
fi

# Get the last assistant message from transcript
# Transcript is JSONL - find last line with role=assistant
# Use tail -r on macOS (tac on Linux)
if command -v tac &> /dev/null; then
    reverse_cmd="tac"
else
    reverse_cmd="tail -r"
fi

last_assistant_msg=$($reverse_cmd "$transcript_path" 2>/dev/null | while read -r line; do
    role=$(echo "$line" | jq -r '.role // .type // empty' 2>/dev/null)
    if [ "$role" = "assistant" ]; then
        echo "$line" | jq -r '.content // .message // empty' 2>/dev/null
        break
    fi
done)

if [ -z "$last_assistant_msg" ]; then
    echo '{"decision": "APPROVE"}'
    exit 0
fi

# Convert to lowercase for matching
msg_lower=$(echo "$last_assistant_msg" | tr '[:upper:]' '[:lower:]')

# --- Synthesis Detection ---
# Phrases indicating Claude is combining/concluding from multiple sources
if echo "$msg_lower" | grep -qE "in conclusion|putting (this|these|it all) together|this suggests that|combining these|taken together|synthesizing|the key (insight|takeaway)|overall[,.]|in summary|bottom line|the honest truth|my (take|recommendation|verdict)|if i were (starting|building)|to summarize|tldr|tl;dr"; then
    cat << 'EOF'
{
  "decision": "block",
  "reason": "Synthesis detected in your response. Call sage_autosave_check with trigger_event='synthesis' to checkpoint this research progress before stopping."
}
EOF
    exit 0
fi

# --- Branch Point Detection ---
# Phrases indicating decision points or multiple paths
if echo "$msg_lower" | grep -qE "we could (either|go with)|two (main )?approaches|option (a|b|1|2|one|two)|alternatively[,.]|on one hand.*on the other|trade-?off|versus|choice between|fork in"; then
    cat << 'EOF'
{
  "decision": "block",
  "reason": "Branch point detected. You identified multiple approaches. Call sage_autosave_check with trigger_event='branch_point' to checkpoint before stopping."
}
EOF
    exit 0
fi

# --- Constraint Discovery Detection ---
# Phrases indicating discovered limitations or blockers
if echo "$msg_lower" | grep -qE "this means we can.?t|won.?t work because|unfortunately.*limit|blocked by|constraint|show-?stopper|deal-?breaker|rules out|eliminates the possibility|can.?t do.*because"; then
    cat << 'EOF'
{
  "decision": "block",
  "reason": "Constraint discovered. Call sage_autosave_check with trigger_event='constraint_discovered' to checkpoint this finding before stopping."
}
EOF
    exit 0
fi

# --- Topic Shift Detection ---
# Phrases indicating moving to a new topic (harder to detect reliably)
if echo "$msg_lower" | grep -qE "moving on to|let.?s (now )?turn to|shifting (focus|gears)|on a (different|separate) note|changing topics|now.*let.?s (look at|consider)"; then
    cat << 'EOF'
{
  "decision": "block",
  "reason": "Topic shift detected. Call sage_autosave_check with trigger_event='topic_shift' to checkpoint before moving on."
}
EOF
    exit 0
fi

# No semantic triggers detected - allow stop
echo '{"decision": "approve"}'
