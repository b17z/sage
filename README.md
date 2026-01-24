# Sage

**Stop losing context. Start checkpointing your AI research.**

Sage is a Claude Code plugin that gives your AI assistant memory across sessions. When you're deep in research or complex problem-solving, Sage helps Claude automatically save semantic checkpoints—capturing what matters (conclusions, tensions, discoveries) and discarding what doesn't (the meandering path to get there).

## The Problem

You're 2 hours into a research session with Claude. You've explored 15 sources, validated 3 hypotheses, found a critical disagreement between experts, and synthesized a thesis. Then:

- Context window fills up → auto-compaction loses your nuanced findings
- You close the session → tomorrow you start from scratch
- You switch projects → that research thread is orphaned

**The result:** You become the orchestration layer, manually maintaining state across fragmented chat sessions like a conspiracy board.

## The Solution

Sage teaches Claude to checkpoint proactively—not when tokens run out, but when something meaningful happens:

- Hypothesis validated or invalidated
- Critical constraint discovered
- Synthesis moment ("putting this together...")
- Branch point ("we could either X or Y")
- You say "checkpoint" or "save this"

Each checkpoint captures:
- **Core question** — What decision is this driving toward?
- **Thesis + confidence** — Your current synthesized position
- **Open questions** — What's still unknown
- **Sources** — Decision-relevant summaries (not full content)
- **Tensions** — Where credible sources disagree (high value!)
- **Unique contributions** — What YOU discovered, not just aggregated

## Quick Start

### 1. Install

```bash
# From PyPI (recommended)
pip install claude-sage[mcp]

# Or from source
git clone https://github.com/b17z/sage.git
cd sage
pip install -e ".[mcp]"
```

### 2. Configure Claude Code

Add to your `.mcp.json` (project or `~/.claude/.mcp.json` for global):

```json
{
  "mcpServers": {
    "sage": {
      "command": "sage-mcp"
    }
  }
}
```

Or install hooks for auto-checkpoint detection:

```bash
sage hooks install
```

### 3. Test it

```bash
# Start Claude Code
claude

# Have a conversation, do some research
# Sage MCP tools are now available to Claude
# Claude will checkpoint automatically on synthesis moments

# Later, list your checkpoints:
sage checkpoint list
sage checkpoint show <checkpoint-id>
```

### 4. Add to Your Project (Recommended)

Add this to your project's `CLAUDE.md` to ensure Claude uses Sage:

```markdown
## Sage Memory

You have Sage MCP tools for persistent memory. **Use them.**

### Session Start
Call `sage_health()` to check for continuity from previous sessions.

### After Web Searches
Call `sage_autosave_check(trigger_event="web_search_complete", core_question="...", current_thesis="...", confidence=0.X)`

### When Synthesizing
Call `sage_autosave_check(trigger_event="synthesis", ...)` when concluding.

### Before Topic Changes
Call `sage_autosave_check(trigger_event="topic_shift", ...)` before moving on.

### Save Knowledge
Call `sage_save_knowledge(knowledge_id="...", content="...", keywords=[...])` for reusable insights.

### Recall Knowledge
Call `sage_recall_knowledge(query="...")` before starting work.
```

See [docs/CLAUDE_SNIPPET.md](docs/CLAUDE_SNIPPET.md) for the full snippet.

## Features

### Auto-Checkpoint (MCP Server)

Claude automatically saves checkpoints when meaningful events occur:

| Trigger | When | Confidence |
|---------|------|------------|
| `synthesis` | Claude combines sources into a conclusion | 0.5 |
| `web_search_complete` | After research with findings | 0.3 |
| `topic_shift` | Conversation changes direction | 0.4 |
| `branch_point` | Decision point identified | 0.4 |
| `constraint_discovered` | Critical limitation found | 0.4 |
| `precompact` | Before context compaction | 0.0 (always) |
| `manual` | You say "checkpoint" | 0.0 (always) |

### Knowledge Persistence

Store and recall facts across sessions:

```bash
# Save knowledge
sage knowledge add "GDPR requires consent" --id gdpr-consent --keywords gdpr,consent

# Query knowledge (auto-recalls on matching keywords)
sage knowledge match "What about GDPR?"

# List all knowledge
sage knowledge list
```

### Semantic Embeddings

Sage uses local embeddings for semantic matching:

- **Model:** `BAAI/bge-large-en-v1.5` (~1.3GB, downloaded on first use)
- **Hybrid scoring:** 70% semantic + 30% keyword matching (configurable)
- **Checkpoint deduplication:** Skips saving when thesis is 90%+ similar
- **Query prefix support:** Optimized retrieval for BGE models

### Project-Local Checkpoints

Checkpoints can be stored per-project:

```bash
# In a project directory
mkdir .sage  # Checkpoints go here instead of ~/.sage

# Or explicitly
sage checkpoint list --project /path/to/project
```

### Checkpoint Templates

Customize checkpoint format:

```bash
sage templates list                    # List available templates
sage_save_checkpoint(..., template="decision")  # Use decision template
```

Built-in templates: `default`, `research`, `decision`, `code-review`

### Knowledge Types

Different recall behavior by type:

| Type | Threshold | Use Case |
|------|-----------|----------|
| `knowledge` | 0.70 | General facts |
| `preference` | 0.30 | User preferences (aggressive recall) |
| `todo` | 0.40 | Persistent reminders |
| `reference` | 0.80 | On-demand reference |

```bash
sage todo list      # List todos
sage todo done <id> # Mark complete
```

### Configurable Thresholds

Tune retrieval and detection via `~/.sage/tuning.yaml` or `.sage/tuning.yaml`:

```yaml
# Retrieval thresholds
recall_threshold: 0.70      # Knowledge recall sensitivity (0-1)
dedup_threshold: 0.90       # Checkpoint deduplication threshold
embedding_weight: 0.70      # Weight for semantic similarity
keyword_weight: 0.30        # Weight for keyword matching

# Embedding model
embedding_model: BAAI/bge-large-en-v1.5
```

Project config overrides user config. See `sage config` commands.

## Storage Format

Checkpoints are stored as **Markdown with YAML frontmatter** (Obsidian-compatible):

```markdown
---
id: 2026-01-16T14-30-00_payment-rails-synthesis
type: checkpoint
confidence: 0.75
trigger: synthesis
skill: crypto-payments
---

# Where do stablecoins win vs traditional payment rails?

## Thesis
Integrate, don't replace. Stablecoins win middle-mile + new primitives,
not POS checkout. Most companies have pieces but not packaging.

## Open Questions
- What's the unified customer object strategy?
- Timeline for Stripe's full stack vs current fragmentation?

## Sources
- **sheel_mohnot** (person): No forcing function for stablecoin POS — _contradicts_
- **simon_taylor** (person): Not about price—about TAM expansion — _nuances_

## Tensions
- **sheel_mohnot** vs **sam_broner**: Whether merchant profitability is sufficient — _unresolved_

## Unique Contributions
- **discovery**: Platform team didn't know about existing SDK integration
```

Checkpoints live in `~/.sage/checkpoints/` (global) or `.sage/checkpoints/` (project-local).

## CLI Reference

```bash
# Checkpoints
sage checkpoint list              # List all checkpoints
sage checkpoint show <id>         # Show checkpoint details
sage checkpoint rm <id>           # Delete a checkpoint

# Knowledge
sage knowledge list               # List all knowledge items
sage knowledge add <file>         # Add knowledge from file
sage knowledge match "query"      # Test what would be recalled
sage knowledge rm <id>            # Remove knowledge item

# Config
sage config list                  # Show current config
sage config set <key> <value>     # Set a value (user-level)
sage config set <key> <value> --project  # Set project-level
sage config reset                 # Reset tuning to defaults

# MCP/Hooks
sage mcp install                  # Install MCP server
sage hooks install                # Install Claude Code hooks

# Admin
sage admin rebuild-embeddings     # Rebuild all embeddings
```

## MCP Tools

Available to Claude via MCP:

| Tool | Purpose |
|------|---------|
| `sage_save_checkpoint` | Save full checkpoint with thesis, sources, tensions |
| `sage_load_checkpoint` | Restore checkpoint context |
| `sage_list_checkpoints` | List all checkpoints |
| `sage_autosave_check` | Auto-checkpoint with confidence thresholds |
| `sage_save_knowledge` | Persist facts with keyword triggers |
| `sage_recall_knowledge` | Query knowledge base semantically |
| `sage_list_knowledge` | List knowledge items |
| `sage_remove_knowledge` | Delete knowledge items |

## Hooks

Claude Code hooks for automatic detection:

| Hook | Purpose |
|------|---------|
| `post-response-semantic-detector.sh` | Detects synthesis, branch points, constraints, topic shifts |
| `post-response-context-check.sh` | Triggers checkpoint at 70% context usage |
| `pre-compact.sh` | Checkpoints before `/compact` (approves auto-compact) |

Hooks have:
- **Priority ordering:** topic_shift > branch_point > constraint > synthesis
- **Cooldown mechanism:** Prevents duplicate triggers
- **Meta-ban list:** Avoids trigger loops on hook discussion

## Prerequisites

- Python 3.11+
- [Claude Code](https://claude.ai/code) CLI
- jq (for hooks)

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — System design and data flow
- [Features](docs/FEATURES.md) — Complete feature reference
- [Checkpoint Methodology](docs/checkpoint.md) — Full framework for semantic checkpointing
- [Hooks](docs/hooks.md) — Hook system documentation
- [Security](docs/security-deserialization-checklist.md) — Security practices

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,mcp]"

# Run tests (869 tests)
pytest tests/ -v

# Lint and format
ruff check sage/ --fix
black sage/
```

## License

MIT
