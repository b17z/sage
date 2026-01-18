# Sage Roadmap

Version timeline and planned features.

## Current: v1.x (January 2026)

### What's Shipped

**Core Checkpointing:**
- Manual and automatic checkpoint triggers
- Full checkpoint schema (thesis, sources, tensions, contributions)
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
- 206 tests covering all modules
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
| Test coverage | Done | 206 tests |
| CLI `sage config` commands | Done | list/set/reset subcommands |
| Storage structure refactor | Done | Secrets vs shareable split |
| Security hardening | Done | File permissions, ReDoS protection |

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
| Depth thresholds | Prevent shallow/noisy checkpoints |

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

## v2.3 (Future)

### Focus: Todos Primitive

| Feature | Description |
|---------|-------------|
| Todo tracking | Persist across sessions |
| Todo checkpointing | Save/restore todo state |
| Integration | Link todos to checkpoints |

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
| v0.2 | Jan 2026 | Security fix (pickle vulnerability) |
| v1.0 | Jan 2026 | Knowledge system, hooks, embeddings |
| v1.x | Jan 2026 | Project-local, config system, markdown format |

---

## Contributing

Priority areas for contribution:
1. Test coverage for edge cases
2. Documentation improvements
3. Hook pattern refinements
4. Cross-platform testing

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design.
