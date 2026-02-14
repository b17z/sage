#!/bin/bash
# PreCompact hook for Sage
# Saves an emergency checkpoint before compaction, then allows
# compaction to proceed. The watcher daemon will detect compaction
# and create a continuity marker pointing to this checkpoint.
#
# This hook fires for both manual (/compact) and auto compaction.
# We always save and allow - blocking is counterproductive.

# Check if sage CLI is available
if ! command -v sage &> /dev/null; then
    echo '{"continue": true}'
    exit 0
fi

# Save emergency checkpoint (fast local extraction, no Claude)
result=$(sage checkpoint emergency --project "$(pwd)" 2>&1)
if [ $? -eq 0 ]; then
    # Extract checkpoint ID from result for logging
    checkpoint_id=$(echo "$result" | grep -o '2[0-9]\{3\}-[0-9]\{2\}-[0-9]\{2\}T[0-9-]*_[a-z0-9-]*' | head -1)
    if [ -n "$checkpoint_id" ]; then
        echo "{\"continue\": true, \"message\": \"Emergency checkpoint saved: $checkpoint_id\"}"
    else
        echo '{"continue": true, "message": "Emergency checkpoint saved"}'
    fi
else
    # Failed to save but still allow compaction
    echo '{"continue": true, "message": "Warning: Could not save emergency checkpoint"}'
fi
exit 0
