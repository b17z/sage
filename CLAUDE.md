# Sage

Semantic memory for Claude Code. Automatically checkpoint research at meaningful moments, persist knowledge across sessions, and never lose context to compaction again.

**Current version:** v3.2.0 (git-aware intelligence)
**Test count:** 1517 tests (maintain or increase)

---

## Skills: Methodology in Skills, Not Here

Sage uses **Claude Skills** for progressive disclosure:

```bash
sage skills install   # Install Sage methodology skills
sage skills list      # Show installed skills
```

This installs:
- **sage-memory** — Background Task pattern for saves
- **sage-research** — Checkpoint methodology (when/how to checkpoint)
- **sage-session** — Session start ritual
- **sage-knowledge** — Knowledge recall and save patterns
- **sage-knowledge-hygiene** — Detect and fix stale knowledge

Skills load **on-demand** when context matches, keeping this file lean.

See [docs/skills.md](docs/skills.md) for the full architecture.

---

## Quick Reference

```bash
# Checkpoints
sage checkpoint list         # List saved checkpoints
sage checkpoint show <id>    # Show checkpoint details

# Knowledge
sage knowledge list          # List stored knowledge
sage knowledge add <file> --id <id> --keywords <kw1,kw2>
sage knowledge match "query" # Test what would be recalled

# Skills
sage skills install          # Install Sage methodology skills
sage skills list             # List installed skills
sage skills update           # Update to latest versions

# Config
sage config list             # Show current config
sage config set <key> <val>  # Set a value

# Session Continuity
sage watcher start           # Start compaction watcher daemon
sage watcher stop            # Stop watcher
sage watcher status          # Check watcher status
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| **System** | |
| `sage_version()` | Get version + config info |
| `sage_health()` | System diagnostics + continuity injection |
| `sage_get_config()` | Show all config values |
| `sage_set_config(key, value)` | Set tuning parameter |
| `sage_reload_config()` | Apply config changes |
| `sage_debug_query(query)` | Debug retrieval scoring |
| **Checkpoints** | |
| `sage_save_checkpoint(...)` | Save research checkpoint |
| `sage_list_checkpoints()` | List saved checkpoints |
| `sage_load_checkpoint(id)` | Load checkpoint for context |
| `sage_search_checkpoints(query)` | Semantic search |
| `sage_autosave_check(...)` | Auto-checkpoint at breakpoints |
| **Knowledge** | |
| `sage_save_knowledge(...)` | Save new knowledge item |
| `sage_recall_knowledge(query)` | Retrieve matching knowledge |
| `sage_list_knowledge()` | List all knowledge |
| `sage_update_knowledge(id, ...)` | Edit existing item |
| `sage_deprecate_knowledge(id, reason)` | Mark as outdated |
| `sage_archive_knowledge(id)` | Hide from recall |
| `sage_remove_knowledge(id)` | Delete item |
| **Todos** | |
| `sage_list_todos()` | List persistent todos |
| `sage_mark_todo_done(id)` | Mark todo complete |
| `sage_get_pending_todos()` | Get pending for injection |

## Architecture

```
~/.sage/                     # User-level (NEVER in repos - contains secrets)
├── config.yaml              # API key, model preferences
├── tuning.yaml              # User-level threshold defaults
├── checkpoints/             # Global checkpoints
└── knowledge/               # Global knowledge

~/.claude/skills/sage/       # Sage methodology skills (installed)
├── sage-memory/SKILL.md
├── sage-research/SKILL.md
├── sage-session/SKILL.md
├── sage-knowledge/SKILL.md
└── sage-knowledge-hygiene/SKILL.md

skills/                      # Skill source files (edit here)
├── sage-memory/SKILL.md
├── sage-research/SKILL.md
├── sage-session/SKILL.md
├── sage-knowledge/SKILL.md
└── sage-knowledge-hygiene/SKILL.md

<project>/.sage/             # Project-level (shareable via git)
├── checkpoints/             # Research checkpoints (team context)
├── knowledge/               # Knowledge base (team insights)
├── tuning.yaml              # Project-specific thresholds
└── local/                   # GITIGNORED - project-local overrides
```

## Key Modules

| File | Purpose |
|------|---------|
| `sage/mcp_server.py` | MCP tools for Claude Code |
| `sage/checkpoint.py` | Checkpoint schema, save/load, maintenance |
| `sage/knowledge.py` | Knowledge storage, retrieval, caching |
| `sage/embeddings.py` | Embedding model, similarity |
| `sage/git.py` | Git context capture, staleness detection |
| `sage/atomic.py` | Atomic file write utilities |
| `sage/default_skills.py` | Sage methodology skill templates |
| `sage/skill.py` | Research skill management |
| `sage/continuity.py` | Session continuity markers |
| `sage/watcher.py` | Compaction watcher daemon |
| `sage/plugins/` | Watcher plugin system |
| `sage/config.py` | Config management |
| `sage/cli.py` | Click CLI |
| `sage/errors.py` | Result types (`Ok`/`Err`) |

## Development

```bash
pip install -e ".[dev]"     # Install dev mode
ruff check sage/ --fix      # Lint
black sage/                 # Format
pytest                      # Run tests
```

### Releasing

```bash
# Check version sync
python scripts/bump_version.py --check

# Bump version (updates pyproject.toml, __init__.py, plugin.json, marketplace.json, CLAUDE.md)
python scripts/bump_version.py 3.3.0

# Then commit and tag
git add -A && git commit -m "chore: bump version to 3.3.0"
git tag v3.3.0
git push && git push --tags
```

```bash
pytest tests/ -v                    # Run all tests
pytest tests/test_embeddings.py -v  # Run specific test file
pytest tests/ -k "test_config"      # Run matching tests
pytest tests/ --cov=sage            # Coverage report
```

## Core Principles

1. **Functional over OOP** — Pure functions, immutable data, errors as values
2. **Tests are mandatory** — Every feature needs unit + integration tests
3. **Config is user-tunable** — Thresholds should be configurable
4. **Graceful degradation** — Features work without optional dependencies
5. **Progressive disclosure** — Methodology in skills, not always-loaded docs

## Code Style

- Python 3.11+ (`match` statements, type parameter syntax)
- Frozen dataclasses for immutability
- 100 char line length
- Functional: pure functions, avoid mutable state

## Testing Patterns

```python
# Unit test — isolated function
def test_function_does_expected_thing():
    result = function_under_test(input)
    assert result == expected

# Integration test — full workflow
def test_feature_end_to_end():
    session = create_test_session()
    session.do_thing()
    assert session.state == expected_state

# Edge case — boundaries and errors
def test_handles_empty_input():
    result = function_under_test([])
    assert result == sensible_default
```

## Don't Forget

- [ ] Run tests before AND after changes
- [ ] New features need tests (unit + integration)
- [ ] Update test count in this file when adding tests
- [ ] Config values from `get_config()`, not hardcoded
- [ ] Install skills: `sage skills install`

## Presenting Sage Output

MCP tool results return structured data. **Always format Sage outputs nicely** rather than showing raw JSON. See `sage-research` and `sage-knowledge` skills for presentation guidelines.

Quick reference:
- **Checkpoints**: Show as research summaries with thesis, evidence, sources
- **Knowledge**: Show with source attribution and code links
- **Code links**: Use `file.py:line` or `file.py::symbol` format
- **Staleness**: `[!]` = code changed, `[+]` = supports, `[~]` = context
