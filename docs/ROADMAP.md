# Sage Roadmap

Version timeline and planned features.

## Current: v3.2.0 (February 2026)

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
- Code-linked knowledge with staleness detection

**Code Intelligence (v3.1+):**
- AST-aware code indexing (Python, TypeScript, Go, Rust, Solidity)
- Semantic code search via embeddings
- Symbol lookup and function analysis
- Core files for session context injection
- Knowledge → code linking with staleness markers

**Git-Aware Features (v3.2):**
- Git context capture in checkpoints (branch, commit, dirty state)
- Code staleness detection via git diff
- Local web UI for browsing checkpoints/knowledge

**Session Continuity:**
- Compaction watcher daemon
- Continuity markers for state preservation
- Auto-injection on session start

**Configuration:**
- SageConfig with tunable thresholds
- Project → user → default cascade
- `tuning.yaml` for retrieval parameters

**Infrastructure:**
- 1517 tests covering all modules
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

All planned v2.0 features shipped. Debug functionality now in `sage debug` (v2.2).

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

## v2.2 (Shipped)

### Focus: Advanced Retrieval + Knowledge Management

| Feature | Status | Description |
|---------|--------|-------------|
| `sage debug` command | Done | Unified retrieval debugging (knowledge + checkpoints) |
| Knowledge edit | Done | `sage knowledge edit` - update content/keywords/status |
| Knowledge deprecate | Done | `sage knowledge deprecate` - mark outdated with reason |
| Knowledge archive | Done | `sage knowledge archive` - hide from recall |

---

## v2.3 (Shipped)

### Focus: Structural Trigger Detection

| Feature | Status | Description |
|---------|--------|-------------|
| Structural triggers | Done | Topic drift detection, convergence signals |
| 70/30 hybrid scoring | Done | Embeddings (70%) + patterns (30%) for triggers |
| Linguistic detection | Done | Pattern matching for trigger phrases |
| Hook integration | Done | Semantic detector uses structural analysis |

---

## v2.4 (Shipped)

### Focus: Session Continuity

| Feature | Status | Description |
|---------|--------|-------------|
| Compaction watcher | Done | Daemon monitors JSONL for compaction events |
| Continuity markers | Done | Preserve state across compaction |
| Auto-injection | Done | Context restored on first tool call |
| CLI commands | Done | `sage watcher start/stop/status`, `sage continuity status` |

---

## v2.5 (Shipped)

### Focus: Proactive Recall + Auto-Injection

| Feature | Status | Description |
|---------|--------|-------------|
| Project context detection | Done | Detect project from dir, git, pyproject, package.json |
| Proactive recall | Done | Auto-recall knowledge matching project context |
| Auto-injection on first call | Done | Session context on any first sage tool call |
| Lower recall threshold | Done | 0.4 threshold for proactive (vs 0.7 normal) |

---

## v2.6 (Shipped)

### Focus: Skills Architecture

| Feature | Status | Description |
|---------|--------|-------------|
| Sage methodology skills | Done | `sage-memory`, `sage-research`, `sage-session` |
| Skills install command | Done | `sage skills install/list/update/show` |
| Lean CLAUDE.md | Done | Moved methodology to skills (335 → 182 lines) |
| Progressive disclosure | Done | Skills load on-demand when context matches |
| Path sanitization | Done | Security hardening for skill paths |

**The Split:**
- CLAUDE.md → Tool reference only (always loaded)
- Skills → Methodology (load on-demand)
- MCP → Memory storage (always available)

See [docs/skills.md](skills.md) for architecture details.

---

## v2.7 (Shipping)

### Focus: Skills Refactor

| Feature | Status | Description |
|---------|--------|-------------|
| Skills from source directory | Done | Skills read from `skills/` directory, not hardcoded |
| 5 default skills | Done | Added `sage-knowledge`, `sage-knowledge-hygiene` |
| Single source of truth | Done | `skills/` dir is authoritative, `sage skills install` copies |
| Removed hardcoded content | Done | ~400 lines of embedded skill strings removed |

**Skills:**
- `sage-memory` — Background Task pattern for saves
- `sage-research` — Checkpoint methodology (merged from old checkpoint skill)
- `sage-session` — Session start ritual
- `sage-knowledge` — Knowledge recall and save patterns
- `sage-knowledge-hygiene` — Knowledge maintenance

---

## v2.8 (Planned)

### Focus: Token Economics & Observability

| Feature | Description |
|---------|-------------|
| Token savings tracking | `sage usage savings` CLI showing compression ratio |
| Session cost comparison | "Checkpoint + knowledge = X tokens vs ~100K full replay" |
| Savings dashboard | Cumulative token/cost savings over time |
| MCP savings tool | `sage_session_savings()` - real-time savings for current session |
| Restore event logging | Track when checkpoints are loaded for analytics |

---

## v2.9 (Planned)

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
| v2.2.0 | Jan 2026 | Knowledge updates: debug, edit, deprecate, archive commands, 675 tests |
| v2.3.0 | Jan 2026 | Structural trigger detection, 70/30 hybrid scoring, 780 tests |
| v2.4.0 | Jan 2026 | Session continuity, compaction watcher daemon, 850 tests |
| v2.5.0 | Jan 2026 | Proactive recall, auto-injection on first tool call, 884 tests |
| v2.6.0 | Jan 2026 | Skills architecture, methodology in skills, lean CLAUDE.md, 932 tests |
| v2.7.0 | Jan 2026 | Skills refactor, 5 skills from source dir, removed hardcoded content, 1025 tests |
| v3.0.0 | Feb 2026 | Plugin architecture, session tracking, watcher plugins, 1200 tests |
| v3.1.0 | Feb 2026 | Code indexing, semantic code search, code-linked knowledge, 1400 tests |
| v3.2.0 | Feb 2026 | Git context, local web UI, CoWork plugin structure, 1517 tests |

---

## Contributing

Priority areas for contribution:
1. Test coverage for edge cases
2. Documentation improvements
3. Hook pattern refinements
4. Cross-platform testing

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design.
