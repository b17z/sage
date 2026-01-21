# Sage

Semantic memory for Claude Code. Automatically checkpoint research at meaningful moments, persist knowledge across sessions, and never lose context to compaction again.

**Current version:** v2.0.1 (async operations, Task polling, structured logging)
**Test count:** 578 tests (maintain or increase)

## Quick Reference

```bash
# Checkpoints
sage checkpoint list         # List saved checkpoints
sage checkpoint show <id>    # Show checkpoint details

# Knowledge management
sage knowledge list          # List stored knowledge
sage knowledge add <file> --id <id> --keywords <kw1,kw2>
sage knowledge match "query" # Test what would be recalled
sage knowledge rm <id>       # Remove knowledge item

# Configuration
sage config list             # Show current config
sage config set <key> <val>  # Set a value
```

## Architecture

```
~/.sage/                     # User-level (NEVER in repos - contains secrets)
├── config.yaml              # API key, model preferences
├── tuning.yaml              # User-level threshold defaults
├── tasks/                   # Async task result files
├── checkpoints/             # Global checkpoints
└── knowledge/               # Global knowledge

<project>/.sage/             # Project-level (shareable via git)
├── checkpoints/             # Research checkpoints (team context)
├── knowledge/               # Knowledge base (team insights)
├── tuning.yaml              # Project-specific thresholds
└── local/                   # GITIGNORED - project-local overrides
```

## Key Modules

| File | Purpose |
|------|---------|
| `sage/mcp_server.py` | MCP tools for Claude Code (async) |
| `sage/checkpoint.py` | Checkpoint schema, save/load |
| `sage/knowledge.py` | Knowledge storage, retrieval, hybrid scoring |
| `sage/embeddings.py` | Embedding model, similarity functions |
| `sage/tasks.py` | Async task infrastructure, task polling |
| `sage/config.py` | Config management, path constants |
| `sage/cli.py` | Click CLI - all commands |
| `sage/errors.py` | Result types (`Ok`/`Err`), error constructors |

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
def save_checkpoint(cp: Checkpoint) -> Result[Path, SageError]:
    if is_duplicate(cp):
        return err(duplicate_checkpoint(cp.id))
    return ok(write_checkpoint(cp))
```

**Checkpoint flow:**
1. Claude detects checkpoint moment (synthesis, branch point, etc.)
2. Calls `sage_save_checkpoint` or `sage_autosave_check` MCP tool
3. Task queued, "📋 Queued" returned immediately
4. Worker validates, generates embeddings, writes to `.sage/checkpoints/`
5. Claude can poll for completion via Task subagent

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
sage config set poll_agent_type general-purpose  # Poll agent type
sage config set poll_agent_model haiku           # Poll agent model
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

## What's Shipped in v2.0

- ✅ Config system with cascade (project → user → default)
- ✅ CLI config commands (`sage config list/set/reset`)
- ✅ Storage structure (secrets vs shareable split)
- ✅ BGE-large embeddings with query prefix
- ✅ Checkpoint templates (default, research, decision, code-review)
- ✅ Knowledge types (knowledge, preference, todo, reference)
- ✅ Context hydration (key_evidence, reasoning_trace)
- ✅ Depth thresholds (prevent shallow checkpoints)
- ✅ Async operations with Task polling notifications
- ✅ Graceful shutdown with task persistence

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

1. Knowledge items stored in project's `.sage/knowledge/` with keyword triggers
2. On query, matching keywords scored via hybrid retrieval (70% semantic + 30% keyword)
3. Recalled knowledge injected into context via MCP tools
4. Use `sage_recall_knowledge(query)` to retrieve relevant knowledge

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

## REQUIRED: Sage Background Operations

Sage write operations block for 2-5 seconds (embedding generation + I/O). **ALWAYS** run them via background Task subagent to avoid blocking the main conversation.

**ALWAYS** use background Task for these MCP tools:
- `sage_save_checkpoint`
- `sage_save_knowledge`
- `sage_autosave_check`

**NEVER** call these directly from the main conversation.

**Pattern:**
```
Task(subagent_type='general-purpose', model='haiku', run_in_background=true,
     prompt='Call sage_save_checkpoint with core_question="...", thesis="...", confidence=0.X, trigger="...". Return the result.')
```

The subagent calls the MCP tool, waits for completion, and returns. You get a native `<task-notification>` when done.

**Legacy async mode:** For advanced use cases, set `sage config set async_enabled true` to use queue-based async with polling. This is opt-in and not recommended for most users.

## Don't Forget

- [ ] Run tests before AND after changes
- [ ] New features need tests (unit + integration)
- [ ] Update test count in this file when adding tests
- [ ] Config values should come from `get_config()`, not hardcoded
