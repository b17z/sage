#!/bin/bash
# Sage MCP server runner for CoWork VM
# Installs dependencies on first run, then starts the MCP server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"  # plugins/sage
SAGE_ROOT="$(dirname "$(dirname "$PLUGIN_ROOT")")"   # repo root (for pyproject.toml)

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

    # Check Python version (need 3.12+)
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
        echo "[Sage] Error: Python 3.12+ required, found $PY_VERSION" >&2
        exit 1
    fi

    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    # If running from source repo, use editable install for development
    if [ -f "$SAGE_ROOT/pyproject.toml" ]; then
        "$VENV_DIR/bin/pip" install --quiet -e "$SAGE_ROOT[mcp,code]"
    else
        "$VENV_DIR/bin/pip" install --quiet "claude-sage[mcp,code]"
    fi
    echo "[Sage] Installation complete" >&2
fi

# Run the MCP server
exec "$VENV_DIR/bin/sage-mcp" "$@"
