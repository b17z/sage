#!/bin/bash
# Sage MCP server runner for CoWork VM
# Installs dependencies on first run, then starts the MCP server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
SAGE_ROOT="$(dirname "$PLUGIN_ROOT")"

# Use workspace for persistent data (survives VM resets)
# CoWork mounts the workspace at a known path
if [ -n "$CLAUDE_WORKSPACE" ]; then
    export SAGE_HOME="$CLAUDE_WORKSPACE/.sage"
else
    export SAGE_HOME="$HOME/.sage"
fi

# Create sage home if needed
mkdir -p "$SAGE_HOME"

# Check if we need to install
VENV_DIR="$SAGE_HOME/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[Sage] First run - installing dependencies..." >&2
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet "claude-sage[mcp]"
    echo "[Sage] Installation complete" >&2
fi

# Run the MCP server
exec "$VENV_DIR/bin/sage-mcp" "$@"
