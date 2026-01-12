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
#
# Uses cooldown markers to prevent repeated firing after checkpoint.

COOLDOWN_SECONDS=${SAGE_SEMANTIC_COOLDOWN:-300}  # 5 minute cooldown per trigger type

input=$(cat)

# Extract session ID and transcript path
session_id=$(echo "$input" | jq -r '.session_id // empty')
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')

if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
    echo '{"decision": "approve"}'
    exit 0
fi

# Use ~/.sage/cooldown/ instead of /tmp for security (predictable /tmp paths risk symlink attacks)
cooldown_dir="${HOME}/.sage/cooldown"
mkdir -p "$cooldown_dir"

# Function to check cooldown for a trigger type
check_cooldown() {
    local trigger_type="$1"
    local marker_file="${cooldown_dir}/semantic_${session_id}_${trigger_type}"
    
    if [ -f "$marker_file" ]; then
        local marker_time=$(cat "$marker_file")
        local current_time=$(date +%s)
        local elapsed=$((current_time - marker_time))
        if [ "$elapsed" -lt "$COOLDOWN_SECONDS" ]; then
            return 0  # In cooldown
        fi
    fi
    return 1  # Not in cooldown
}

# Function to set cooldown for a trigger type
set_cooldown() {
    local trigger_type="$1"
    local marker_file="${cooldown_dir}/semantic_${session_id}_${trigger_type}"
    date +%s > "$marker_file"
}

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
    echo '{"decision": "approve"}'
    exit 0
fi

# Convert to lowercase for matching
msg_lower=$(echo "$last_assistant_msg" | tr '[:upper:]' '[:lower:]')

# --- Strip Quotes and Code Blocks ---
# Use perl for reliable cross-platform regex (BSD sed on macOS has limited support)
msg_stripped=$(echo "$msg_lower" | perl -0777 -pe '
    s/```.*?```//gs;           # Remove fenced code blocks
    s/`[^`]+`//g;              # Remove inline code
    s/"[^"]*"//g;              # Remove double-quoted strings
    s/^>.*$//gm;               # Remove blockquotes
')

# --- Meta-discussion Ban List ---
# Skip detection if message is about the hook/checkpoint system itself
# (use msg_lower here since we want to catch meta-discussion even in quotes)
if echo "$msg_lower" | grep -qE "(hook|checkpoint|trigger|pattern|detector|cooldown|sage_autosave).*(fire|detect|block|test)|test.*summary|trigger.*loop"; then
    echo '{"decision": "approve"}'
    exit 0
fi

# --- Pattern Detection (priority order: most actionable first) ---

# --- Topic Shift Detection (HIGHEST PRIORITY) ---
# Signals context change - checkpoint before losing previous context
if echo "$msg_stripped" | grep -qE "moving on to|let.?s (now )?turn to|shifting (focus|gears)|on a (different|separate) note|changing topics|now.*let.?s (look at|consider)"; then
    if ! check_cooldown "topic_shift"; then
        set_cooldown "topic_shift"
        cat << 'EOF'
{
  "decision": "block",
  "reason": "Topic shift detected. Call sage_autosave_check with trigger_event='topic_shift' to checkpoint before moving on."
}
EOF
        exit 0
    fi
fi

# --- Branch Point Detection ---
# Decision point - capture the options before choosing
if echo "$msg_stripped" | grep -qE "we could (either|go with)|two (main )?approaches|option (a|b|1|2|one|two)|alternatively[,.]|on one hand.*on the other|trade-?off|versus|choice between|fork in"; then
    if ! check_cooldown "branch_point"; then
        set_cooldown "branch_point"
        cat << 'EOF'
{
  "decision": "block",
  "reason": "Branch point detected. You identified multiple approaches. Call sage_autosave_check with trigger_event='branch_point' to checkpoint before stopping."
}
EOF
        exit 0
    fi
fi

# --- Constraint Discovery Detection ---
# Blocker found - important pivot point
if echo "$msg_stripped" | grep -qE "this means we can.?t|won.?t work because|unfortunately.*limit|blocked by|show-?stopper|deal-?breaker|rules out|eliminates the possibility|can.?t do.*because"; then
    if ! check_cooldown "constraint"; then
        set_cooldown "constraint"
        cat << 'EOF'
{
  "decision": "block",
  "reason": "Constraint discovered. Call sage_autosave_check with trigger_event='constraint_discovered' to checkpoint this finding before stopping."
}
EOF
        exit 0
    fi
fi

# --- Synthesis Detection (LOWEST PRIORITY - catch-all) ---
# Phrases indicating Claude is combining/concluding from multiple sources
if echo "$msg_stripped" | grep -qE "in conclusion|putting (this|these|it all) together|this suggests that|combining these|taken together|synthesizing|the key (insight|takeaway)|overall[,.]|in summary|bottom line|the honest truth|my (take|recommendation|verdict)|if i were (starting|building)|to summarize|tldr|tl;dr"; then
    if ! check_cooldown "synthesis"; then
        set_cooldown "synthesis"
        cat << 'EOF'
{
  "decision": "block",
  "reason": "Synthesis detected in your response. Call sage_autosave_check with trigger_event='synthesis' to checkpoint this research progress before stopping."
}
EOF
        exit 0
    fi
fi

# No semantic triggers detected - allow stop
echo '{"decision": "approve"}'
