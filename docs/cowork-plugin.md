# Sage CoWork Plugin

Sage can be installed as a CoWork/Claude Code plugin, providing slash commands and skills for semantic memory.

## Installation

### From GitHub (when published)
```bash
# Add to plugin marketplace
claude plugin marketplace add benvy/sage

# Install
claude plugin install sage@benvy/sage
```

### Local Development
```bash
# Clone the repo
git clone https://github.com/benvy/sage
cd sage

# Install Sage
pip install -e ".[mcp]"

# Link as local plugin
claude plugin link .
```

## Plugin Structure

```
sage/
├── .claude-plugin/
│   ├── plugin.json       # Plugin manifest
│   └── mcp.json          # MCP server config
├── commands/
│   ├── checkpoint.md     # /sage:checkpoint
│   ├── recall.md         # /sage:recall
│   ├── knowledge.md      # /sage:knowledge
│   └── session.md        # /sage:session
└── skills/
    ├── sage-memory/      # Background save patterns
    ├── sage-research/    # Checkpoint methodology
    ├── sage-session/     # Session start ritual
    ├── sage-knowledge/   # Knowledge management
    └── sage-knowledge-hygiene/  # Stale knowledge detection
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/sage:checkpoint` | Save or list research checkpoints |
| `/sage:checkpoint list` | List recent checkpoints |
| `/sage:checkpoint save` | Save current research state |
| `/sage:checkpoint load <id>` | Load a checkpoint |
| `/sage:checkpoint search <query>` | Search checkpoints |
| `/sage:recall [topic]` | Recall relevant knowledge |
| `/sage:knowledge` | Manage knowledge base |
| `/sage:knowledge list` | List all knowledge |
| `/sage:knowledge add` | Add new knowledge |
| `/sage:session` | Check session status |
| `/sage:session health` | Full system diagnostic |

## Skills

Skills are loaded automatically when context matches their triggers:

- **sage-memory** — Triggers on: save, background, async
- **sage-research** — Triggers on: research, synthesis, checkpoint
- **sage-session** — Triggers on: session start, continuity
- **sage-knowledge** — Triggers on: recall, remember, knowledge
- **sage-knowledge-hygiene** — Triggers on: stale, outdated, review

## MCP Tools

The plugin exposes these MCP tools:

### Checkpoints
- `sage_save_checkpoint` — Save a research checkpoint
- `sage_list_checkpoints` — List saved checkpoints
- `sage_load_checkpoint` — Load checkpoint for context
- `sage_search_checkpoints` — Semantic search
- `sage_autosave_check` — Auto-checkpoint at trigger moments

### Knowledge
- `sage_save_knowledge` — Save new knowledge
- `sage_recall_knowledge` — Recall matching knowledge
- `sage_list_knowledge` — List all knowledge
- `sage_update_knowledge` — Update existing item
- `sage_deprecate_knowledge` — Mark as outdated
- `sage_archive_knowledge` — Hide from recall
- `sage_remove_knowledge` — Delete permanently

### Code Context
- `sage_index_code` — Index codebase for search
- `sage_search_code` — Semantic code search
- `sage_grep_symbol` — Fast exact symbol lookup
- `sage_analyze_function` — Get function source
- `sage_code_context` — Find knowledge linking to code

### Session
- `sage_health` — System diagnostics
- `sage_continuity_status` — Check/inject continuity context

## Team Usage

Push `.sage/` to your repo for team-shared context:

```bash
# In your project
git add .sage/
git commit -m "Add Sage knowledge base"
git push
```

Teammates who install the Sage plugin will automatically have access to:
- Team checkpoints (research history)
- Team knowledge (shared insights)
- Project-specific tuning

## CoWork Integration

In CoWork, Sage enables:
1. **Persistent research context** — Checkpoints survive compaction
2. **Team knowledge sharing** — `.sage/` in repo = team memory
3. **Code-linked insights** — Knowledge items link to code locations
4. **Automatic context injection** — Relevant knowledge auto-surfaces
