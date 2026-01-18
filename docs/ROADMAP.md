# Sage Roadmap

Version timeline and planned features.

## Current: v1.x (January 2026)

### What's Shipped

**Core Checkpointing:**
- Manual and automatic checkpoint triggers
- Full checkpoint schema (thesis, sources, tensions, contributions)
- Context hydration fields (key_evidence, reasoning_trace) for better restore quality
- Depth threshold enforcement (prevent shallow/noisy checkpoints)
- Checkpoint deduplication via embedding similarity
- Project-local checkpoint support
- Markdown + frontmatter storage format (Obsidian-compatible)

**Knowledge System:**
- Knowledge storage with keyword triggers
- Hybrid retrieval (70% semantic + 30% keyword)
- Skill-scoped knowledge
- Automatic recall on query match

**Hooks:**
- Semantic detector (synthesis, branch_point, constraint, topic_shift)
- Context threshold detector (70% usage)
- Pre-compact hook (manual vs auto-compact handling)
- Priority ordering and cooldown mechanisms

**Configuration:**
- SageConfig with tunable thresholds
- Project → user → default cascade
- `tuning.yaml` for retrieval parameters

**Infrastructure:**
- 231 tests covering all modules
- Safe deserialization (yaml.safe_load, allow_pickle=False)
- Path sanitization for security
- File permissions (chmod 0o600) for sensitive data

---

## v2.0 (In Progress)

### Focus: Polish and Documentation

| Feature | Status | Notes |
|---------|--------|-------|
| Config system | Done | SageConfig with cascade |
| Markdown format | Done | Checkpoints + knowledge |
| README overhaul | Done | Reflects current state |
| ARCHITECTURE.md | Done | System design + flowcharts |
| FEATURES.md | Done | Complete feature reference |
| ROADMAP.md | Done | This document |
| Test coverage | Done | 231 tests |
| CLI `sage config` commands | Done | list/set/reset subcommands |
| Storage structure refactor | Done | Secrets vs shareable split |
| Security hardening | Done | File permissions, ReDoS protection |
| Context hydration fields | Done | key_evidence, reasoning_trace |
| Depth thresholds | Done | Prevent shallow checkpoints |
| Checkpoint search | Done | Semantic search across checkpoints |

### Remaining v2.0 Work

| Feature | Priority | Notes |
|---------|----------|-------|
| Embedding model upgrade | Low | mxbai-embed-large option |
| `sage knowledge debug` | Medium | Transparency for retrieval tuning |

---

## v2.1 (Planned)

### Focus: Advanced Retrieval

| Feature | Description |
|---------|-------------|
| Freshness decay | Recent knowledge weighted higher |
| Cross-project search | Priority cascade (project → global with boost) |
| Knowledge versioning | History array for updates |
| Structural triggers | Topic drift detection, convergence signals |

---

## v2.2 (Planned)

### Focus: PKM Integration

| Feature | Description |
|---------|-------------|
| Obsidian mode | Optional vault integration |
| Wikilink support | `[[checkpoints/id]]` references |
| Graph visualization | Checkpoint/knowledge relationships |
| Conflict resolution | Human-in-the-loop for sync issues |

---

## v2.3 (Next Priority)

### Focus: Type-Aware Knowledge

Unify memory primitives under knowledge with a `type` field.

**Schema Change:**
```yaml
---
id: example-item
type: knowledge | preference | todo | reference
status: pending | done  # For todos only
keywords: [...]
---
Content here...
```

**Types and Behavior:**

| Type | Save Trigger | Recall Behavior |
|------|--------------|-----------------|
| `knowledge` | Manual (user curates) | Query match (threshold: 0.70) |
| `preference` | Semi-auto ("I always...", "I prefer...") | Aggressive (threshold: 0.30) or session-start |
| `todo` | Auto ("TODO", "remind me", "later") | Session-start + keyword match |
| `reference` | Manual | Lower priority, on-demand |

**Features:**

| Feature | Description |
|---------|-------------|
| `type` field on knowledge | Enable different recall/save behaviors |
| Preference detection hook | Detect "I always...", "I prefer...", confirm save |
| Todo detection hook | Detect "TODO", "remind me", auto-save |
| `sage todo list/done` CLI | Manage persistent todos |
| Session-start recall | Surface pending todos + active preferences |
| Full session loading | Optional escape hatch to load raw transcript |

**Why not separate primitives?**
- Knowledge already has storage, indexing, recall infrastructure
- Type field changes behavior without new systems
- Checkpoints stay separate (rich schema: sources, tensions, etc.)

---

## Future Ideas

### Code-Specific Patterns
- Detect refactors, bug fixes, architecture decisions
- Code-aware checkpoint triggers
- Test coverage checkpoints

### Multi-Platform Support
- Codex adapter
- Gemini adapter
- Generic LLM interface

### Advanced Features
- Context window tracker MCP tool
- Auto knowledge extraction from checkpoints
- Content-hash cooldown (smarter dedup)
- Checkpoint branching (try different approaches)

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| v0.1 | Jan 2026 | Initial release, basic checkpointing |
| v0.2 | Jan 2026 | Semantic embeddings, checkpoint dedup, security fix |
| v1.0 | Jan 2026 | Config system, CLI subcommands, security hardening, 206 tests |
| v1.1 | Jan 2026 | Context hydration, depth thresholds, checkpoint search, 231 tests |

---

## Contributing

Priority areas for contribution:
1. Test coverage for edge cases
2. Documentation improvements
3. Hook pattern refinements
4. Cross-platform testing

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design.
