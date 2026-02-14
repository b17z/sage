#!/bin/bash
# SessionStart hook for Sage continuity
#
# This hook fires on every session start (new, resume, clear, compact).
# It does two things:
# 1. Restarts the watcher scoped to the current project
# 2. Injects any pending continuity context

# Check if sage CLI is available
if ! command -v sage &> /dev/null; then
    exit 0
fi

# Get current project directory (cwd is the project root)
PROJECT_DIR="$(pwd)"

# Restart watcher scoped to this project (--force to switch if needed)
# Run in background and suppress output - we don't want to delay session start
sage watcher start --project "$PROJECT_DIR" --force >/dev/null 2>&1 &

# Check continuity status and inject context if pending
output=$(sage continuity inject 2>/dev/null)

if [ -n "$output" ]; then
    echo "$output"
fi
