# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Overview

Sage is a research orchestration CLI that manages "skills" - specialized AI research personas powered by Claude. Skills are stored in `~/.claude/skills/` (standard Agent Skills location) while Sage metadata lives in `~/.sage/skills/`.

## Development Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run CLI
sage --help
sage list
sage ask <skill> "<query>"

# Lint and format
ruff check sage/
ruff check sage/ --fix
black sage/

# Run tests (pytest, no tests exist yet)
pytest
```

## Architecture

### Directory Layout
- `sage/cli.py` — Click-based CLI entry point, all commands defined here
- `sage/client.py` — Anthropic API wrapper with streaming and retry logic
- `sage/config.py` — Config management, path constants (`SAGE_DIR`, `SKILLS_DIR`, etc.)
- `sage/skill.py` — Skill CRUD operations, SKILL.md parsing, context building
- `sage/history.py` — JSONL-based interaction logging and usage analytics
- `sage/memory.py` — Shared memory (cross-skill insights in `~/.sage/shared_memory.md`)
- `sage/errors.py` — Result types (`Ok`/`Err`) and error constructors
- `sage/init.py` — First-time setup wizard
- `sage/reference/` — Bundled markdown docs copied to `~/.sage/reference/` on init
- `sage/templates/hooks/` — Claude Code hook templates

### Key Patterns

**Result Types (errors as values)**
```python
from sage.errors import Result, SageError, ok, err

def load_skill(name: str) -> Result[Skill, SageError]:
    if not skill_exists:
        return err(skill_not_found(name))
    return ok(skill)

# Usage: pattern match on result.ok
result = load_skill("privacy")
if not result.ok:
    handle_error(result.error)
skill = result.value
```

**Skill Data Flow**
1. Skills defined in `~/.claude/skills/<name>/SKILL.md` with YAML frontmatter
2. `load_skill()` parses frontmatter, loads docs from `docs/`, injects shared memory
3. `build_context()` assembles full system prompt from skill + docs
4. `send_message()` streams response via Anthropic API with caching enabled
5. `append_entry()` logs interaction to `~/.sage/skills/<name>/history.jsonl`

**Path Constants** (in `config.py`)
- `SAGE_DIR` = `~/.sage/`
- `SKILLS_DIR` = `~/.claude/skills/`
- `SHARED_MEMORY_PATH` = `~/.sage/shared_memory.md`

### API Client Details

The client uses:
- Streaming responses with text callback
- Ephemeral cache control on system prompts
- Web search tool (configurable)
- Automatic retry with exponential backoff for rate limits

### CLI Structure

All commands in `cli.py` follow the pattern:
1. Load config with `Config.load()`
2. Call domain function (skill.py, client.py, etc.)
3. Check `result.ok`, format errors with `format_error()`
4. Use Rich console for output

## Code Style

- Python 3.11+ (uses `match` statements, type parameter syntax)
- Dataclasses with `frozen=True` for immutability
- 100 char line length (ruff + black configured)
- Functional style: prefer pure functions, avoid mutable state
