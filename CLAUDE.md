# Sage

Research orchestration CLI that manages "skills" - specialized AI research personas powered by Claude. Implements semantic checkpointing for preserving context across conversations.

**Current version:** v1.x → v2.0 upgrade
**Test count:** 206 tests (maintain or increase)

## Quick Reference

```bash
sage list                    # List all skills
sage ask <skill> "<query>"   # One-shot query
sage context <skill>         # Show what a skill knows
sage history <skill>         # Query history
sage usage                   # Token/cost analytics

# Knowledge management
sage knowledge list          # List stored knowledge
sage knowledge add <file> --id <id> --keywords <kw1,kw2>
sage knowledge match "query" # Test what would be recalled
sage knowledge rm <id>       # Remove knowledge item
```

## Architecture

```
~/.sage/                     # User-level (NEVER in repos - contains secrets)
├── config.yaml              # API key, model preferences
├── tuning.yaml              # User-level threshold defaults
├── embeddings/              # Binary embedding caches
└── skills/<name>/
    └── history.jsonl        # Interaction log

<project>/.sage/             # Project-level (shareable via git)
├── checkpoints/             # Research checkpoints (team context)
├── knowledge/               # Knowledge base (team insights)
├── tuning.yaml              # Project-specific thresholds
└── local/                   # GITIGNORED - project-local overrides

~/.claude/skills/            # Skill definitions (Agent Skills standard)
└── <name>/
    ├── SKILL.md             # System prompt + YAML frontmatter
    └── docs/                # Reference materials
```

## Key Modules

| File | Purpose |
|------|---------|
| `sage/cli.py` | Click CLI - all commands |
| `sage/client.py` | Anthropic API with streaming, retry, caching |
| `sage/skill.py` | Skill CRUD, SKILL.md parsing, context building |
| `sage/history.py` | JSONL logging, usage analytics |
| `sage/errors.py` | Result types (`Ok`/`Err`), error constructors |
| `sage/config.py` | Config management, path constants |
| `sage/knowledge.py` | Knowledge storage, retrieval, hybrid scoring |
| `sage/embeddings.py` | Embedding model, similarity functions |
| `sage/checkpoint.py` | Checkpoint schema, save/load |
| `sage/mcp_server.py` | MCP tools for Claude Code |
| `sage/triggers/` | v2.0: structural, linguistic, combiner |

## Documentation Hierarchy

| Doc | When to Load | Size |
|-----|--------------|------|
| `sage-code-spec-v2.md` | **Always** — implementation guide | ~15KB |
| `sage-memory-framework-v2.5.md` | Design rationale questions only | ~65KB |
| `ARCHITECTURE.md` | System overview needed | TBD |

**Default:** Load only `sage-code-spec-v2.md`. It has everything needed for implementation.

## Patterns

**Result types (errors as values):**
```python
def load_skill(name: str) -> Result[Skill, SageError]:
    if not skill_exists:
        return err(skill_not_found(name))
    return ok(skill)
```

**Skill data flow:**
1. `SKILL.md` parsed (YAML frontmatter + content)
2. Docs from `docs/` loaded
3. Shared memory injected
4. Context built via `build_context()`
5. Streamed via Anthropic API with ephemeral cache
6. Logged to `history.jsonl`

## Development

```bash
pip install -e ".[dev]"     # Install dev mode
ruff check sage/ --fix      # Lint
black sage/                 # Format
pytest                      # Run tests
```

**Testing commands:**
```bash
pytest tests/ -v                    # Run all tests
pytest tests/test_embeddings.py -v  # Run specific test file
pytest tests/ -k "test_config"      # Run matching tests
pytest tests/ --cov=sage            # Coverage report
pytest tests/ --cov=sage --cov-report=term-missing
```

**Manual testing:**
```bash
sage status                         # Check Sage state
sage knowledge match "query"        # Test what would be recalled
sage config list                    # Show config
sage config set recall_threshold 0.65
sage config set recall_threshold 0.60 --project  # Project-level
sage config reset                   # Reset tuning to defaults
sage admin rebuild-embeddings       # After model swap
```

## Core Principles

1. **Functional over OOP** — Pure functions, immutable data, errors as values
2. **Tests are mandatory** — Every feature needs unit + integration tests
3. **Config is user-tunable** — Thresholds should be configurable, not hardcoded
4. **Graceful degradation** — Features should work without optional dependencies

## Code Style

- Python 3.11+ (`match` statements, type parameter syntax)
- Frozen dataclasses for immutability
- 100 char line length
- Functional: pure functions, avoid mutable state

## Testing Patterns

**Every feature implementation MUST include:**

```python
# Unit test — isolated function
def test_function_does_expected_thing():
    result = function_under_test(input)
    assert result == expected

# Integration test — full workflow
def test_feature_end_to_end():
    # Setup
    session = create_test_session()

    # Action
    session.do_thing()

    # Assert
    assert session.state == expected_state

# Edge case — boundaries and errors
def test_handles_empty_input():
    result = function_under_test([])
    assert result == sensible_default  # No crash
```

## v2.0 Implementation Order

1. ✅ **Config system** (`sage/config.py`) — Foundation for tunable thresholds
2. ✅ **CLI config commands** — `sage config list/set/reset` subcommands
3. ✅ **Storage structure** — Secrets vs shareable split, security hardening
4. **Embedding upgrade** — Swap model, add query prefix
5. **Knowledge debug** — Uses config, shows tuning tips
6. **Structural detection** — Uses config thresholds
7. **Trigger combiner** — Uses structural + linguistic
8. **Checkpoint key_evidence** — Schema extension

Each step: implement → test → commit.

## Checkpoint Methodology (docs/checkpoint.md)

Core principle: **Compress to reconstruction point, not verbatim.**

Checkpoint at state transitions (proactive), not token pressure (reactive):
- Hypothesis validated/invalidated
- Topic transition
- Critical constraint discovered
- Branch point
- Synthesis moment

Schema preserves: core_question, thesis, confidence, open_questions, sources, tensions, unique_contributions, action context.

## Knowledge Recall

Automatic injection of stored insights based on query keywords:

1. Knowledge items stored in `~/.sage/knowledge/` with keyword triggers
2. On query, matching keywords are scored and relevant items recalled
3. Recalled knowledge injected into context before API call
4. User sees "📚 Knowledge recalled (N)" notification

See `skills/knowledge/SKILL.md` for the auto-invoke skill.

## Research Task Completion (REQUIRED)

A research task is NOT complete until:
1. ✅ Answer provided to user
2. ✅ `sage_autosave_check` called with appropriate trigger

**NEVER skip step 2.** The research is incomplete without it.

Workflow: `WebSearch → synthesize → sage_autosave_check → respond`

Trigger events:
- `web_search_complete` — after processing search results
- `synthesis` — when concluding ("therefore", "in summary")
- `topic_shift` — before changing subjects

## Hook Message Response (REQUIRED)

When a Stop hook injects a message (e.g., "🔍 Synthesis detected..."), you MUST act on it.

Hook detection triggers:
- 🔍 **Synthesis detected** → Call `sage_autosave_check(trigger_event='synthesis', ...)`
- 🔀 **Branch point detected** → Call `sage_autosave_check(trigger_event='branch_point', ...)`  
- 🚧 **Constraint discovered** → Call `sage_autosave_check(trigger_event='constraint_discovered', ...)`
- ↪️ **Topic shift detected** → Call `sage_autosave_check(trigger_event='topic_shift', ...)`

**NEVER ignore hook detection messages.** They indicate checkpoint-worthy moments.

## Planned Features (docs/design-knowledge-checkpoints.md)

- **Chat Mode**: Multi-turn REPL with `/checkpoint`, `/restore` commands
- **Checkpoint Restore**: Resume from saved checkpoints
- **Checkpoint Branching**: Try different approaches from same point

---

## Don't Forget

- [ ] Run tests before AND after changes
- [ ] New features need tests (unit + integration)
- [ ] Update test count in this file when adding tests
- [ ] Config values should come from `get_config()`, not hardcoded
- [ ] Structural triggers INITIATE, linguistic triggers CONFIRM
