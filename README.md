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

## Prerequisites

**For the Claude Code plugin (recommended):**
- [Claude Code](https://claude.ai/code) CLI installed
- Git (to clone this repo)
- No Python required

**For the optional Python CLI (`sage ask`, `sage chat`):**
- Python 3.11+
- pip

## Installation

### Claude Code Plugin (Recommended)

```bash
# 1. Clone to a permanent location
git clone https://github.com/b17z/sage.git ~/plugins/sage

# 2. Run Claude Code with the plugin
claude --plugin-dir ~/plugins/sage
```

This loads Sage for the current session. The checkpoint and knowledge skills are now available.

**For persistent use**, add an alias to your shell config:
```bash
# ~/.zshrc or ~/.bashrc
alias claude-sage='claude --plugin-dir ~/plugins/sage'
```

Now you can run `claude-sage` from any directory—checkpoints and knowledge are stored globally in `~/.sage/`, so your research persists across projects.

### Optional: Python CLI

If you also want the standalone `sage` CLI for use outside Claude Code:

```bash
cd ~/plugins/sage
pip install -e .
```

This gives you commands like `sage ask <skill> "query"` and `sage chat <skill>`.

### Optional: MCP Server (Tool-Based)

For direct tool execution (Claude calls tools instead of outputting YAML for you to copy):

```bash
# Install with MCP support
cd ~/plugins/sage
pip install -e ".[mcp]"
```

Add to Claude Code's MCP config (`~/.config/claude-code/mcp.json`):

```json
{
  "mcpServers": {
    "sage": {
      "command": "python",
      "args": ["-m", "sage.mcp_server"]
    }
  }
}
```

This exposes tools: `sage_save_checkpoint`, `sage_list_checkpoints`, `sage_load_checkpoint`, `sage_save_knowledge`, `sage_recall_knowledge`, `sage_list_knowledge`, `sage_remove_knowledge`.

## Usage

### Automatic (Recommended)

Just work normally. Claude will recognize checkpoint-worthy moments and save state automatically. You'll see brief notifications like:

```
Checkpointed: "Validated that Clark airport is closer than Manila"
```

### Manual

Say "checkpoint" or "save this" anytime:

```
You: checkpoint
Claude: [Extracts and saves semantic checkpoint]
        Saved: core question, thesis (confidence: 0.8), 3 open questions,
        5 sources, 1 tension, 2 unique discoveries
```

### Slash Command

Use `/checkpoint` for explicit control:

```
/checkpoint
```

### Restore

Start a new session and reference a previous checkpoint:

```
You: Continue from where I left off on the payment rails research
Claude: [Loads checkpoint, continues seamlessly]
```

## What Gets Saved

Checkpoints live in `~/.sage/checkpoints/` (global, accessible from any project).

Example checkpoint (98% compression from 45,000 token conversation):

```yaml
checkpoint:
  id: 2026-01-10T14-30-00_payment-rails-synthesis

  core_question: |
    Where do stablecoins actually win vs traditional payment rails?

  thesis: |
    Integrate, don't replace. Stablecoins win middle-mile + new primitives,
    not POS checkout. Most companies have pieces but not packaging.
  confidence: 0.75

  open_questions:
    - What's the unified customer object strategy?
    - Timeline for Stripe's full stack vs current fragmentation?

  sources:
    - id: sheel_mohnot
      take: "No forcing function for stablecoin POS—every successful payment network had exclusivity or killer reward"
      relation: contradicts
    - id: simon_taylor
      take: "Not about price—about TAM expansion. Stablecoins enable payments that couldn't exist before"
      relation: nuances

  tensions:
    - between: [sheel_mohnot, sam_broner]
      nature: "Whether merchant profitability is sufficient forcing function"
      resolution: unresolved

  unique_contributions:
    - type: discovery
      content: "Platform team didn't know about existing SDK integration possibilities"
```

## Architecture

Sage is built as a multi-platform plugin:

```
sage/
├── skills/checkpoint/       # Core skill (works across platforms)
├── sage/mcp_server.py       # MCP server for auto-checkpoint
├── .claude-plugin/          # Claude Code adapter
├── hooks/                   # Claude Code hooks
├── commands/                # Slash commands
├── WARP.md                  # Warp adapter
└── docs/                    # Methodology documentation
```

Future adapters can be added for Codex, Gemini, etc. The core checkpoint methodology remains shared.

## Why "Semantic" Checkpointing?

Traditional approaches compress reactively (when tokens run out) and lossily (summarizing everything equally).

Semantic checkpointing is:
- **Proactive** — Triggered by state transitions, not token pressure
- **Selective** — Preserves high-value signals (tensions, discoveries), drops low-value (tangents, process chatter)
- **Decision-oriented** — Organized around the question being answered, not chronology

The compression test: *"If I only had this checkpoint, could I make the same decision I would with the full conversation?"*

## Documentation

- [Checkpoint Methodology](docs/checkpoint.md) — Full framework for semantic checkpointing
- [Design Doc](docs/design-knowledge-checkpoints.md) — Implementation details and future roadmap
- [MCP Design](docs/design-mcp-autocheckpoint.md) — MCP server architecture for auto-checkpoint

## License

MIT
