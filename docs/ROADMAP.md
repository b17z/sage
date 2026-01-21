# Sage Roadmap

Version timeline and planned features.

## Current: v2.1.x (January 2026)

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
- 578 tests covering all modules
- Safe deserialization (yaml.safe_load, allow_pickle=False)
- Path sanitization for security
- File permissions (chmod 0o600) for sensitive data

---

## v2.0 (Shipped)

### Focus: Polish and Documentation

| Feature | Status | Notes |
|---------|--------|-------|
| Config system | Done | SageConfig with cascade |
| Markdown format | Done | Checkpoints + knowledge |
| README overhaul | Done | Reflects current state |
| ARCHITECTURE.md | Done | System design + flowcharts |
| FEATURES.md | Done | Complete feature reference |
| ROADMAP.md | Done | This document |
| Test coverage | Done | 535 tests |
| CLI `sage config` commands | Done | list/set/reset subcommands |
| Storage structure refactor | Done | Secrets vs shareable split |
| Security hardening | Done | File permissions, ReDoS protection |
| Context hydration fields | Done | key_evidence, reasoning_trace |
| Depth thresholds | Done | Prevent shallow checkpoints |
| Checkpoint search | Done | Semantic search across checkpoints |
| Embedding model upgrade | Done | BGE-large-en-v1.5 (1024 dims, +7 MTEB) |
| Knowledge types | Done | knowledge, preference, todo, reference |
| Checkpoint templates | Done | default, research, decision, code-review |

### v2.0 Async (Shipped)

| Feature | Status | Notes |
|---------|--------|-------|
| Async checkpoint/knowledge saves | Done | Non-blocking with Task polling |
| Background model warmup | Done | Don't block for 30+ sec download |
| Graceful shutdown | Done | Pending tasks persisted for restart |
| Task polling pattern | Done | Native Claude Code task notifications |
| Security: removed bash watcher | Done | v2.0.1 - bash glob patterns were exploitable |

### Remaining v2.0 Work

| Feature | Priority | Notes |
|---------|----------|-------|
| `sage knowledge debug` | Medium | Transparency for retrieval tuning |

---

## v2.1 (Shipped)

### Focus: Simplified Architecture + CI Automation

| Feature | Status | Notes |
|---------|--------|-------|
| Simplified async architecture | Done | Sync Sage + CLAUDE.md enforced Task subagent |
| Background Task pattern | Done | Non-blocking via `run_in_background=true` |
| Auto-version CI workflow | Done | GitHub Actions auto-bumps on release |
| Version sync across files | Done | pyproject.toml, plugin.json, marketplace.json |

---

## v2.2 (Planned)

### Focus: Advanced Retrieval + Knowledge Management

| Feature | Description |
|---------|-------------|
| Freshness decay | Recent knowledge weighted higher |
| Cross-project search | Priority cascade (project → global with boost) |
| Knowledge versioning | History array for updates |
| Knowledge edit/deprecate | Inline update without delete, "deprecated" status |
| `sage knowledge debug` | Transparency for retrieval tuning |

---

## v2.3 (Planned)

### Focus: PKM Integration

| Feature | Description |
|---------|-------------|
| Obsidian mode | Optional vault integration |
| Wikilink support | `[[checkpoints/id]]` references |
| Graph visualization | Checkpoint/knowledge relationships |
| Conflict resolution | Human-in-the-loop for sync issues |

---

## v2.4 (Planned)

### Focus: Advanced Hooks & Triggers

| Feature | Description |
|---------|-------------|
| Structural triggers | Topic drift detection, convergence signals |
| Uncertainty trigger | Detect hedging language as checkpoint moment |
| Hook analytics | Track trigger frequency, false positive rate |

*Note: Async operations originally planned for v2.3 were shipped in v2.0.*

---

## v2.5 (Planned)

### Focus: Token Economics & Observability

| Feature | Description |
|---------|-------------|
| Token savings tracking | `sage usage --savings` shows compression ratio |
| Session cost comparison | "This checkpoint saved X tokens vs full replay" |
| Savings dashboard | Cumulative token/cost savings over time |

---

## v2.6 (Planned)

### Focus: Code-Aware Intelligence

| Feature | Description |
|---------|-------------|
| Code-aware triggers | Detect refactors, architecture decisions, test changes |
| Git-aware checkpoints | Auto-checkpoint on significant commits |
| Code review MCP | Query engineering principles, run senior engineer personas |
| Diff-aware context | Include relevant code changes in checkpoint |

---

## v3.0 (Vision)

### Focus: Proactive Code Intelligence

*"Like Copilot but for engineering principles — watches while you code, not after."*

| Feature | Description |
|---------|-------------|
| Real-time code monitoring | MCP hooks into file saves, analyzes against principles |
| Inline warnings | Surface security/performance/design issues as you write |
| Pattern learning | "You've forgotten input validation 3x" → auto-save as knowledge |
| Research capture | "Why gRPC vs REST?" research → stored as decision knowledge |
| Personalized principles | Learn YOUR patterns, not just generic rules |

**Architecture concept:**

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  File Watch  │────▶│   Analyzer   │────▶│  Principles  │
│  (on save)   │     │  (AST/regex) │     │  (embedded)  │
└──────────────┘     └──────────────┘     └──────────────┘
                            │                    │
                            ▼                    ▼
                     ┌──────────────┐     ┌──────────────┐
                     │   Warnings   │     │   Learning   │
                     │  (inline)    │     │  (patterns)  │
                     └──────────────┘     └──────────────┘
                                                │
                                                ▼
                                         ┌──────────────┐
                                         │  Knowledge   │
                                         │  (auto-save) │
                                         └──────────────┘
```

**Key insight:** Reactive → Proactive. Don't wait for questions, anticipate them.

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
| v2.0 | Jan 2026 | Async operations, Task polling notifications, 535 tests |
| v2.0.1 | Jan 2026 | Security fix: replaced bash watcher with Read-tool polling |
| v2.1.0 | Jan 2026 | Simplified architecture: sync Sage + Task subagent pattern |
| v2.1.1 | Jan 2026 | Auto-version CI workflow, version sync across all files, 578 tests |

---

## Contributing

Priority areas for contribution:
1. Test coverage for edge cases
2. Documentation improvements
3. Hook pattern refinements
4. Cross-platform testing

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design.
