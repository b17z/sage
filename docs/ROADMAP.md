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
- 397 tests covering all modules
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
| Test coverage | Done | 397 tests |
| CLI `sage config` commands | Done | list/set/reset subcommands |
| Storage structure refactor | Done | Secrets vs shareable split |
| Security hardening | Done | File permissions, ReDoS protection |
| Context hydration fields | Done | key_evidence, reasoning_trace |
| Depth thresholds | Done | Prevent shallow checkpoints |
| Checkpoint search | Done | Semantic search across checkpoints |
| Embedding model upgrade | Done | BGE-large-en-v1.5 (1024 dims, +7 MTEB) |
| Knowledge types | Done | knowledge, preference, todo, reference |
| Checkpoint templates | Done | default, research, decision, code-review |

### Remaining v2.0 Work

| Feature | Priority | Notes |
|---------|----------|-------|
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

## v2.3 (Planned)

### Focus: Async/Background Operations

Make Sage non-blocking for better UX during long operations.

| Feature | Description |
|---------|-------------|
| Async checkpoint saves | Fire-and-forget with notification on completion |
| Background model loading | Don't block conversation for 1.3GB download |
| Parallel embedding generation | Batch operations for knowledge rebuild |
| MCP notifications | Signal completion/failure asynchronously |

**Why async?**
- BGE-large first load blocks for 30+ seconds
- Checkpoint saves with embedding generation add latency
- Users shouldn't wait for non-critical operations

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
| v1.2 | Jan 2026 | BGE-large embeddings, checkpoint templates, knowledge types, 397 tests |

---

## Contributing

Priority areas for contribution:
1. Test coverage for edge cases
2. Documentation improvements
3. Hook pattern refinements
4. Cross-platform testing

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design.
