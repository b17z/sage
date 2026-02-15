# Sage Features

Semantic memory for Claude Code — designed for AI agents and learning engineers alike.

> **New to Sage?** Start with the [Feature Guides](./features/README.md) for detailed documentation with code examples.

## The Two Audiences

Sage serves two audiences with different goals:

| Audience | Goal | Key Benefit |
|----------|------|-------------|
| **AI Agents** | Efficiency | Shared memory across context windows |
| **Learning Engineers** | Understanding | Visible, traceable learning process |

The same features serve both — checkpoints help agents resume after compaction *and* help engineers track what they learned.

## Quick Reference

### Core Memory

| Feature | Purpose | Guide |
|---------|---------|-------|
| [Checkpointing](./features/checkpointing.md) | Save research state at meaningful moments | Thesis, evidence, reasoning trace |
| [Knowledge](./features/knowledge.md) | Store and auto-recall reusable insights | Keywords trigger automatic injection |
| [Continuity](./features/continuity.md) | Survive context compaction | Watcher daemon auto-restores |
| [Failure Memory](./features/failure-memory.md) | Learn from what didn't work | Track mistakes, auto-recall *(v4.0)* |

### Invisible Context Hydration (v4.0)

| Feature | Purpose | Guide |
|---------|---------|-------|
| [System Folder](./features/system-folder.md) | Agent-managed pinned content | `.sage/system/` auto-injection |
| [MCP Resources](./features/mcp-resources.md) | Direct `@sage://` data access | No tool calls needed |
| [Knowledge Linking](./features/knowledge-linking.md) | Connect related items | Multi-hop reasoning |
| [Git Versioning](./features/git-versioning.md) | Version history for research | Every save = commit |

### Code Awareness (v3.1)

| Feature | Purpose | Guide |
|---------|---------|-------|
| [Code Context](./features/code-context.md) | Track what code informed your research | files_explored, files_changed, code_refs |
| [Code-Linked Knowledge](./features/knowledge.md#code-linked-knowledge-v31) | Link knowledge to code locations | Forward/reverse lookup, staleness detection |
| [Code Indexing](./features/code-indexing.md) | Semantic search over codebases | Find code by intent, not keywords |
| [Embeddings](./features/embeddings.md) | Dual models for prose and code | BGE for text, CodeSage for code |

### Configuration

| Feature | Purpose | Guide |
|---------|---------|-------|
| [Configuration](./features/configuration.md) | Tunable thresholds and settings | Project and user-level config |
| [Storage Maintenance](./maintenance.md) | Pruning, caching, cleanup | Automatic housekeeping |

## The Sage Loop

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              THE SAGE LOOP                                    │
└──────────────────────────────────────────────────────────────────────────────┘

     ┌──────────┐         ┌──────────┐         ┌──────────┐
     │ Research │────────▶│ Trigger  │────────▶│  Save    │
     │          │         │ detected │         │checkpoint│
     └──────────┘         └──────────┘         └────┬─────┘
          ▲                                         │
          │    ┌──────────────────────────────────┐ │
          │    │        ~/.sage/checkpoints/       │◀┘
          │    │                                  │
          │    │  thesis + reasoning + code_refs  │
          │    │  + open questions + evidence     │
          │    └──────────────────────────────────┘
          │                     │
          │                     ▼
     ┌────┴─────┐         ┌──────────┐         ┌──────────┐
     │ Continue │◀────────│  Inject  │◀────────│Compaction│
     │seamlessly│         │ context  │         │ detected │
     └──────────┘         └──────────┘         └──────────┘
```

## CLI Quick Start

```bash
# Checkpoints
sage checkpoint list              # List saved checkpoints
sage checkpoint show <id>         # Show checkpoint details

# Knowledge
sage knowledge list               # List stored knowledge
sage knowledge match "query"      # Test what would be recalled

# Code (v3.1)
sage index                        # Index current directory
sage search "authentication"      # Semantic code search
sage grep authenticate_user       # Fast symbol lookup

# Config
sage config list                  # Show all settings
sage config set <key> <value>     # Set a value

# Watcher
sage watcher start                # Start compaction watcher
sage watcher status               # Check watcher status
```

## MCP Tools Quick Reference

### Checkpoints
```python
sage_save_checkpoint(core_question, thesis, confidence, ...)
sage_list_checkpoints(limit=10)
sage_load_checkpoint(checkpoint_id)
sage_search_checkpoints(query)
sage_autosave_check(trigger_event, ...)
```

### Knowledge
```python
sage_save_knowledge(knowledge_id, content, keywords, code_links=[], ...)
sage_recall_knowledge(query)       # Returns knowledge + resolved code
sage_code_context(file, symbol)    # Reverse lookup: code → knowledge
sage_list_knowledge()
sage_update_knowledge(knowledge_id, ...)
sage_remove_knowledge(knowledge_id)
```

### Code (v3.1)
```python
sage_index_code(path=".", incremental=True)
sage_search_code(query, limit=10)
sage_grep_symbol(name)
sage_analyze_function(name, project_path)
sage_mark_core(path, summary)
sage_list_core()
```

### System
```python
sage_health()                    # Diagnostics + continuity injection
sage_version()                   # Version info
sage_get_config()                # Current configuration
sage_set_config(key, value)      # Set config value
sage_debug_query(query)          # Debug retrieval scoring
sage_continuity_status()         # Check/inject continuity
```

## The Learning Philosophy

> "Productivity benefits may come at the cost of skills necessary to validate AI-written code if junior engineers' skill development has been stunted by using AI."

Sage addresses this by making the learning process **visible**:

| Traditional AI Use | Sage Approach |
|-------------------|---------------|
| "AI, how does auth work?" | "Where is auth code?" → Read it yourself |
| "Cool, it works!" | Checkpoint: "I understand because..." |
| (did you learn?) | (traceable evidence you did) |

Every checkpoint captures:
- **What you explored** — `files_explored`, `code_refs`
- **What you didn't understand** — `open_questions`
- **How you figured it out** — `reasoning_trace`
- **What you concluded** — `thesis`, `key_evidence`

When you review checkpoints, you see not just *what* you learned but *how* you learned it.

## Storage Layout

```
~/.sage/                          # User-level (secrets, never commit)
├── config.yaml                   # API keys
├── tuning.yaml                   # User defaults
├── checkpoints/                  # Global checkpoints
├── knowledge/                    # Global knowledge
├── embeddings/                   # Embedding caches
└── codebase/lancedb/             # Global code index

<project>/.sage/                  # Project-level (safe to commit)
├── tuning.yaml                   # Project settings
├── checkpoints/                  # Project checkpoints
├── knowledge/                    # Project knowledge
├── codebase/compiled/            # Compiled code index
└── local/                        # GITIGNORED local overrides
```

## Feature Guides

Detailed documentation with code examples and implementation links:

- **[Feature Index](./features/README.md)** — Start here
- [Checkpointing](./features/checkpointing.md) — Research state snapshots
- [Knowledge](./features/knowledge.md) — Reusable insights
- [Continuity](./features/continuity.md) — Compaction recovery
- [Failure Memory](./features/failure-memory.md) — Learn from mistakes *(v4.0)*
- [System Folder](./features/system-folder.md) — Pinned context *(v4.0)*
- [MCP Resources](./features/mcp-resources.md) — Direct data access *(v4.0)*
- [Knowledge Linking](./features/knowledge-linking.md) — Connect items *(v4.0)*
- [Git Versioning](./features/git-versioning.md) — Version history *(v4.0)*
- [Code Context](./features/code-context.md) — File tracking
- [Code Indexing](./features/code-indexing.md) — Semantic code search
- [Embeddings](./features/embeddings.md) — Prose vs code models
- [Configuration](./features/configuration.md) — Tuning options

## Codebase Map

| Feature | Primary Module | Tests |
|---------|---------------|-------|
| Checkpointing | `sage/checkpoint.py` | `tests/test_checkpoint.py` |
| Knowledge | `sage/knowledge.py` | `tests/test_knowledge.py` |
| Failure Memory | `sage/failures.py` | `tests/test_failures.py` |
| System Folder | `sage/system_context.py` | `tests/test_system_context.py` |
| MCP Resources | `sage/mcp_server.py` | `tests/test_mcp_resources.py` |
| Code Context | `sage/transcript.py` | `tests/test_transcript.py` |
| Code Indexing | `sage/codebase/indexer.py` | `tests/test_codebase_indexer.py` |
| Embeddings | `sage/embeddings.py` | `tests/test_embeddings.py` |
| Watcher | `sage/watcher.py` | `tests/test_watcher.py` |
| Plugins | `sage/plugins/` | `tests/test_plugins.py` |
| Configuration | `sage/config.py` | `tests/test_config.py` |
| MCP Server | `sage/mcp_server.py` | `tests/test_mcp_server.py` |

## Version History

- **v4.0** — Invisible context hydration (system folder, failures, resources, linking)
- **v3.2** — Git-aware intelligence, web UI improvements
- **v3.1** — Code-aware features (code context, CodeSage embeddings)
- **v3.0** — Plugin architecture, session tracking
- **v2.5** — Proactive recall, skills system
- **v2.4** — Session continuity, watcher daemon
- **v2.3** — Structural trigger detection
- **v2.0** — Async operations, logging
- **v1.0** — Core checkpointing and knowledge
