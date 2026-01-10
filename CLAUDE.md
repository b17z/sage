# Sage

Research orchestration CLI that manages "skills" - specialized AI research personas powered by Claude. Implements semantic checkpointing for preserving context across conversations.

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
~/.sage/                     # Sage metadata and state
├── config.yaml
├── shared_memory.md         # Cross-skill insights
├── knowledge/               # Knowledge recall system
│   ├── index.yaml           # Registry with triggers
│   ├── global/              # Available to all skills
│   └── skills/<name>/       # Skill-scoped knowledge
└── skills/<name>/
    └── history.jsonl        # Interaction log

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
| `sage/knowledge.py` | Knowledge recall system |

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

## Code Style

- Python 3.11+ (`match` statements, type parameter syntax)
- Frozen dataclasses for immutability
- 100 char line length
- Functional: pure functions, avoid mutable state

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

## Planned Features (docs/design-knowledge-checkpoints.md)

- **Chat Mode**: Multi-turn REPL with `/checkpoint`, `/restore` commands
- **Checkpoint Restore**: Resume from saved checkpoints
- **Checkpoint Branching**: Try different approaches from same point
