#!/bin/bash
# Test suite for Sage Claude Code hooks
# Run with: bash .claude/hooks/test_hooks.sh

# Don't use set -e because bash arithmetic can return non-zero

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASSED=0
FAILED=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

test_hook() {
    local name="$1"
    local hook="$2"
    local input="$3"
    local expected_decision="$4"
    local expected_pattern="$5"
    
    local output
    output=$(echo "$input" | "$SCRIPT_DIR/$hook" 2>/dev/null)
    local decision=$(echo "$output" | jq -r '.decision // empty')
    
    if [ "$decision" = "$expected_decision" ]; then
        if [ -n "$expected_pattern" ]; then
            if echo "$output" | grep -q "$expected_pattern"; then
                echo -e "${GREEN}✓${NC} $name"
                ((PASSED++))
            else
                echo -e "${RED}✗${NC} $name - missing pattern: $expected_pattern"
                echo "  Output: $output"
                ((FAILED++))
            fi
        else
            echo -e "${GREEN}✓${NC} $name"
            ((PASSED++))
        fi
    else
        echo -e "${RED}✗${NC} $name - expected '$expected_decision', got '$decision'"
        echo "  Output: $output"
        ((FAILED++))
    fi
}

echo "=== Sage Hooks Test Suite ==="
echo ""

# --- Context Check Hook Tests ---
echo "## post-response-context-check.sh"

# Create temp transcripts for context testing
CONTEXT_TEMP=$(mktemp -d)

# Clean up any stale cooldown markers from previous test runs
rm -f "${HOME}/.sage/cooldown/checkpoint_test-"* 2>/dev/null

# 50% usage: 100k tokens out of 200k
echo '{"message": {"usage": {"input_tokens": 80000, "output_tokens": 20000, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}' > "$CONTEXT_TEMP/50pct.jsonl"
test_hook "50% usage → approve" \
    "post-response-context-check.sh" \
    "{\"session_id\": \"test-50\", \"transcript_path\": \"$CONTEXT_TEMP/50pct.jsonl\"}" \
    "approve"

# 69% usage: 138k tokens out of 200k (just under 70% threshold)
echo '{"message": {"usage": {"input_tokens": 138000, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}' > "$CONTEXT_TEMP/69pct.jsonl"
test_hook "69% usage → approve" \
    "post-response-context-check.sh" \
    "{\"session_id\": \"test-69\", \"transcript_path\": \"$CONTEXT_TEMP/69pct.jsonl\"}" \
    "approve"

# 70% usage: 140k tokens out of 200k (at threshold)
echo '{"message": {"usage": {"input_tokens": 140000, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}' > "$CONTEXT_TEMP/70pct.jsonl"
test_hook "70% usage → block" \
    "post-response-context-check.sh" \
    "{\"session_id\": \"test-70\", \"transcript_path\": \"$CONTEXT_TEMP/70pct.jsonl\"}" \
    "block" \
    "context_threshold"

# 75% usage: 150k tokens out of 200k
echo '{"message": {"usage": {"input_tokens": 150000, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}' > "$CONTEXT_TEMP/75pct.jsonl"
test_hook "75% usage → block" \
    "post-response-context-check.sh" \
    "{\"session_id\": \"test-75\", \"transcript_path\": \"$CONTEXT_TEMP/75pct.jsonl\"}" \
    "block" \
    "75%"

# Cache tokens counted: input(50k) + cache_read(60k) + cache_creation(40k) = 150k = 75%
echo '{"message": {"usage": {"input_tokens": 50000, "output_tokens": 20000, "cache_read_input_tokens": 60000, "cache_creation_input_tokens": 40000}}}' > "$CONTEXT_TEMP/cache.jsonl"
test_hook "cache tokens counted" \
    "post-response-context-check.sh" \
    "{\"session_id\": \"test-cache\", \"transcript_path\": \"$CONTEXT_TEMP/cache.jsonl\"}" \
    "block" \
    "75%"

# Missing transcript → approve
test_hook "missing transcript → approve" \
    "post-response-context-check.sh" \
    '{"session_id": "test-missing", "transcript_path": "/nonexistent/path.jsonl"}' \
    "approve"

# Cleanup test markers
rm -f "${HOME}/.sage/cooldown/checkpoint_test-"* 2>/dev/null

rm -rf "$CONTEXT_TEMP"

echo ""

# --- Semantic Detector Hook Tests ---
echo "## post-response-semantic-detector.sh"

# Create temp transcripts for testing
TEMP_DIR=$(mktemp -d)

# Clean up semantic cooldown markers
rm -f "${HOME}/.sage/cooldown/semantic_test-"* 2>/dev/null

# Test: synthesis detection (each needs unique session_id)
echo '{"role": "assistant", "content": "In conclusion, REST is better for simple APIs."}' > "$TEMP_DIR/synthesis.jsonl"
test_hook "synthesis: 'in conclusion' → block" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-syn1\", \"transcript_path\": \"$TEMP_DIR/synthesis.jsonl\"}" \
    "block" \
    "synthesis"

echo '{"role": "assistant", "content": "My take is that GraphQL works better here."}' > "$TEMP_DIR/my_take.jsonl"
test_hook "synthesis: 'my take' → block" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-syn2\", \"transcript_path\": \"$TEMP_DIR/my_take.jsonl\"}" \
    "block" \
    "synthesis"

echo '{"role": "assistant", "content": "The bottom line is we should use TypeScript."}' > "$TEMP_DIR/bottom_line.jsonl"
test_hook "synthesis: 'bottom line' → block" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-syn3\", \"transcript_path\": \"$TEMP_DIR/bottom_line.jsonl\"}" \
    "block" \
    "synthesis"

# Test: branch point detection
echo '{"role": "assistant", "content": "We could either use REST or GraphQL for this."}' > "$TEMP_DIR/branch.jsonl"
test_hook "branch point: 'could either' → block" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-branch\", \"transcript_path\": \"$TEMP_DIR/branch.jsonl\"}" \
    "block" \
    "branch_point"

# Test: constraint detection
echo '{"role": "assistant", "content": "This means we cant use that approach because of the rate limit."}' > "$TEMP_DIR/constraint.jsonl"
test_hook "constraint: 'cant...because' → block" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-constraint\", \"transcript_path\": \"$TEMP_DIR/constraint.jsonl\"}" \
    "block" \
    "constraint"

# Test: no trigger
echo '{"role": "assistant", "content": "I have updated the config.json file."}' > "$TEMP_DIR/normal.jsonl"
test_hook "normal message → approve" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-normal\", \"transcript_path\": \"$TEMP_DIR/normal.jsonl\"}" \
    "approve"

# Test: quote stripping - trigger in code block should NOT fire
echo '{"role": "assistant", "content": "Here is an example:\n```python\n# In conclusion, this is the main function\ndef main():\n    pass\n```\nLet me know if you have questions."}' > "$TEMP_DIR/code_block.jsonl"
test_hook "code block: 'in conclusion' → approve (stripped)" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-code1\", \"transcript_path\": \"$TEMP_DIR/code_block.jsonl\"}" \
    "approve"

# Test: quote stripping - trigger in inline code should NOT fire
echo '{"role": "assistant", "content": "You can use the `in conclusion` method to finalize."}' > "$TEMP_DIR/inline_code.jsonl"
test_hook "inline code: 'in conclusion' → approve (stripped)" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-code2\", \"transcript_path\": \"$TEMP_DIR/inline_code.jsonl\"}" \
    "approve"

# Test: quote stripping - trigger in quoted string should NOT fire
echo '{"role": "assistant", "content": "You said \"in conclusion the API is broken\" but I disagree."}' > "$TEMP_DIR/quoted.jsonl"
test_hook "quoted string: 'in conclusion' → approve (stripped)" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-quote1\", \"transcript_path\": \"$TEMP_DIR/quoted.jsonl\"}" \
    "approve"

# Test: trigger outside quotes should still fire
echo '{"role": "assistant", "content": "You said \"the API is broken\" and in conclusion I agree."}' > "$TEMP_DIR/outside_quote.jsonl"
test_hook "outside quote: 'in conclusion' → block" \
    "post-response-semantic-detector.sh" \
    "{\"session_id\": \"test-quote2\", \"transcript_path\": \"$TEMP_DIR/outside_quote.jsonl\"}" \
    "block" \
    "synthesis"

# Test: missing transcript
test_hook "missing transcript → approve" \
    "post-response-semantic-detector.sh" \
    '{"session_id": "test-missing", "transcript_path": "/nonexistent/path.jsonl"}' \
    "approve"

# Cleanup
rm -f "${HOME}/.sage/cooldown/semantic_test-"* 2>/dev/null
rm -rf "$TEMP_DIR"

echo ""

# --- Pre-Compact Hook Test ---
echo "## pre-compact.sh"

output=$(echo '{}' | "$SCRIPT_DIR/pre-compact.sh" 2>/dev/null)
decision=$(echo "$output" | jq -r '.decision // empty')
if [ "$decision" = "block" ] && echo "$output" | grep -q "sage_autosave_check"; then
    echo -e "${GREEN}✓${NC} pre-compact → block with checkpoint instruction"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} pre-compact → expected block with checkpoint instruction"
    ((FAILED++))
fi

echo ""

# --- Summary ---
echo "=== Results ==="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"

if [ $FAILED -gt 0 ]; then
    exit 1
fi
