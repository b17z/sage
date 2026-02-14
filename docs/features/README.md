# Sage Features

Sage is semantic memory for Claude Code — but it's designed for two audiences:

1. **AI Agents** — Efficiency through shared memory, reduced file re-reading
2. **Learning Engineers** — Understanding through traceable research, learning journals

## The Learning Problem

> "Productivity benefits may come at the cost of skills necessary to validate AI-written code if junior engineers' skill development has been stunted by using AI in the first place."

AI tools can give false progress: "Look, I built this app!" (by copy-pasting AI output). The danger isn't getting stuck — it's *not* getting stuck when you should be.

**Sage addresses this by making the learning process visible:**

- Checkpoints capture *why* you concluded something, not just *what*
- Code refs trace conclusions back to the code evidence
- Knowledge items crystallize understanding, not just facts
- Reasoning traces preserve the thinking process

## Feature Categories

### Core Memory
- [Checkpointing](./checkpointing.md) — Save research state at meaningful moments
- [Knowledge System](./knowledge.md) — Store and recall reusable insights
- [Session Continuity](./continuity.md) — Survive context compaction

### Code Awareness
- [Code Context Capture](./code-context.md) — Track what code informed your research
- [Code Indexing](./code-indexing.md) — Semantic search over codebases
- [Embeddings](./embeddings.md) — Dual models for prose and code

### Configuration
- [Configuration](./configuration.md) — Tunable thresholds and settings
- [Storage Maintenance](./maintenance.md) — Pruning, caching, cleanup

### Advanced
- [Trigger Detection](./triggers.md) — Automatic checkpoint moments
- [Plugin Architecture](./plugins.md) — Watcher daemon extensibility
- [Skills](./skills.md) — Methodology as progressive disclosure

## Quick Links

| I want to... | See |
|--------------|-----|
| Save my research progress | [Checkpointing](./checkpointing.md) |
| Remember something for later | [Knowledge System](./knowledge.md) |
| Search code semantically | [Code Indexing](./code-indexing.md) |
| Understand what files I explored | [Code Context Capture](./code-context.md) |
| Configure Sage behavior | [Configuration](./configuration.md) |
| Extend the watcher daemon | [Plugin Architecture](./plugins.md) |

## Design Philosophy

### For Agents: Shared Memory Layer

```
┌──────────────────────────────────────────────────────────────┐
│  Main Agent                                                   │
│  → sage_search_code() → finds relevant code                  │
│  → sage_search_checkpoints() → finds past research           │
│  → sage_save_checkpoint() → captures what was explored       │
└──────────────────────────────────────────────────────────────┘
          │                          │
          ▼                          ▼
┌─────────────────────┐    ┌─────────────────────┐
│  Subagent A         │    │  Subagent B         │
│  sage_recall() →    │    │  sage_recall() →    │
│  gets shared context│    │  gets shared context│
└─────────────────────┘    └─────────────────────┘
```

Agents have separate context windows. Sage lets them share memory without re-reading files.

### For Learning Engineers: Visible Progress

The traditional learning trap:
```
Read tutorial → Copy code → It works → "I learned it!"
                                        (did you though?)
```

The Sage approach:
```
Explore code → Get stuck → Research why → Checkpoint understanding
     ↓              ↓            ↓                 ↓
files_explored  open_questions  sources      reasoning_trace
     ↓              ↓            ↓                 ↓
   "I looked     "I didn't     "This doc      "I now understand
    at these"     get this"     helped"        because..."
```

Every checkpoint is a **learning journal entry** with:
- What code you explored (`files_explored`, `code_refs`)
- What you didn't understand (`open_questions`)
- What helped you understand (`sources`, `key_evidence`)
- How you reasoned through it (`reasoning_trace`)

### The Meta-Learning Benefit

When you review old checkpoints, you're not just remembering conclusions — you're **seeing how you learned**. This meta-awareness is what separates "I used AI to build X" from "I understand how X works."

## Codebase Map

| Feature | Primary Module | Tests |
|---------|---------------|-------|
| Checkpointing | `sage/checkpoint.py` | `tests/test_checkpoint.py` |
| Knowledge | `sage/knowledge.py` | `tests/test_knowledge.py` |
| Code Context | `sage/transcript.py` | `tests/test_transcript.py` |
| Code Indexing | `sage/codebase/indexer.py` | `tests/test_codebase_indexer.py` |
| Embeddings | `sage/embeddings.py` | `tests/test_embeddings.py` |
| Watcher/Plugins | `sage/watcher.py`, `sage/plugins/` | `tests/test_watcher.py` |
| Configuration | `sage/config.py` | `tests/test_config.py` |
| MCP Server | `sage/mcp_server.py` | `tests/test_mcp_server.py` |
