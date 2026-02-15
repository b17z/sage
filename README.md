# Sage

**Memory for Claude Code.** Research → checkpoint → compaction → auto-restore.

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Research   │───▶│ Checkpoint  │───▶│  Compaction │
│  with Claude│    │  (auto)     │    │  happens    │
└─────────────┘    └─────────────┘    └──────┬──────┘
                                             │
┌─────────────┐    ┌─────────────┐           │
│  Continue   │◀───│ Auto-inject │◀──────────┘
│  seamlessly │    │  context    │
└─────────────┘    └─────────────┘
```

## Quick Start

```bash
# 1. Install
pip install claude-sage[mcp]

# 2. Setup (adds MCP server + installs methodology skills)
sage mcp install
sage skills install

# 3. Use Claude - Sage handles the rest
claude
```

That's it. Claude now has memory across sessions.

## How It Works

**The problem:** You're 2 hours into research. Context fills up, auto-compacts, nuanced findings gone. Tomorrow you start from scratch.

**The solution:** Sage checkpoints at meaningful moments—not when tokens run out, but when something worth remembering happens:

| Trigger | Example |
|---------|---------|
| Synthesis | "Therefore, the answer is..." |
| Branch point | "We could either X or Y..." |
| Constraint | "This won't work because..." |
| Topic shift | Conversation changes direction |
| Manual | You say "checkpoint this" |

Each checkpoint captures your **thesis**, **confidence**, **open questions**, **sources**, and **tensions** (where experts disagree).

## What Gets Saved

```markdown
# Where do stablecoins win vs traditional rails?

## Thesis (75% confidence)
Integrate, don't replace. Stablecoins win middle-mile,
not POS checkout.

## Open Questions
- Timeline for Stripe's full stack?

## Tensions
- sheel_mohnot vs sam_broner: merchant profitability — unresolved
```

Checkpoints are Markdown files (Obsidian-compatible) in `~/.sage/checkpoints/` or `.sage/checkpoints/` (project-local).

## The Three Layers

```
┌────────────────────────────────────────────────┐
│  Skills (methodology)                          │
│  sage-memory, sage-research, sage-session      │
│  Load on-demand when context matches           │
├────────────────────────────────────────────────┤
│  MCP Server (tools)                            │
│  sage_save_checkpoint, sage_recall_knowledge   │
│  Always available to Claude                    │
├────────────────────────────────────────────────┤
│  Storage                                       │
│  ~/.sage/checkpoints/, ~/.sage/knowledge/      │
│  Markdown + YAML frontmatter                   │
└────────────────────────────────────────────────┘
```

- **Skills** teach Claude *when* and *how* to checkpoint
- **MCP** gives Claude the *tools* to save/load
- **Storage** persists everything as readable Markdown

## CLI Basics

```bash
sage checkpoint list          # See your checkpoints
sage checkpoint show <id>     # View one
sage knowledge list           # See stored knowledge
sage knowledge match "query"  # Test what would recall
sage skills list              # Check installed skills
sage watcher start            # Auto-detect compaction

# Configuration
sage config list              # View current settings
sage config set checkpoint_max_age_days 30  # Customize storage
sage config set checkpoint_max_count 100    # Cap checkpoints
```

## Visual Interface

```bash
sage ui              # Local web UI at localhost:5555
sage ui --api-only   # REST API for custom frontends
```

Or use any of these:
- **CoWork plugin** — If you have CoWork access
- **Obsidian** — Open `~/.sage/` as vault (it's just Markdown)
- **Custom** — Build on the REST API

See [docs/ui.md](docs/ui.md) for details.

## Learn More

- **[Features](docs/FEATURES.md)** — Complete feature reference
- **[Architecture](docs/ARCHITECTURE.md)** — System design
- **[Skills](docs/skills.md)** — How methodology skills work
- **[Continuity](docs/continuity.md)** — Session persistence deep-dive
- **[Maintenance](docs/maintenance.md)** — Storage maintenance and caching
- **[UI Options](docs/ui.md)** — Web UI, API, Obsidian, CoWork plugin

## Requirements

- Python 3.12+
- [Claude Code](https://claude.ai/code) CLI

## Development

```bash
pip install -e ".[dev,mcp]"
pytest tests/ -v  # 1517 tests
```

## Acknowledgments

Output formatting inspired by [TOON](https://toon-format.org) — a token-efficient notation format for LLMs by [@mixeden](https://github.com/mixeden).

## License

MIT
