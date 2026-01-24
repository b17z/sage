# Sage Features

Complete reference for all Sage capabilities.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              THE SAGE LOOP                                  │
└─────────────────────────────────────────────────────────────────────────────┘

     ┌──────────┐         ┌──────────┐         ┌──────────┐
     │ Research │────────▶│ Trigger  │────────▶│  Save    │
     │          │         │ detected │         │checkpoint│
     └──────────┘         └──────────┘         └────┬─────┘
          ▲                                         │
          │    ┌──────────────────────────────────┐ │
          │    │        ~/.sage/checkpoints/       │◀┘
          │    │                                  │
          │    │  thesis + confidence + sources  │
          │    │  + tensions + open questions    │
          │    └──────────────────────────────────┘
          │                     │
          │                     ▼
     ┌────┴─────┐         ┌──────────┐         ┌──────────┐
     │ Continue │◀────────│  Inject  │◀────────│Compaction│
     │seamlessly│         │ context  │         │ detected │
     └──────────┘         └──────────┘         └──────────┘
```

**Triggers:** synthesis, branch point, constraint, topic shift, manual, context threshold, pre-compact

**Auto-restore:** Watcher daemon detects compaction → injects last checkpoint on next tool call

---

## Checkpointing

### Automatic Checkpoints

Sage detects checkpoint-worthy moments via hooks and prompts Claude to save state.

**Triggers:**

| Trigger | Description | Default Confidence |
|---------|-------------|-------------------|
| `synthesis` | Claude combines multiple sources into a conclusion | 0.5 |
| `web_search_complete` | Research completed with findings | 0.3 |
| `topic_shift` | Conversation changes direction | 0.4 |
| `branch_point` | Decision point identified ("we could X or Y") | 0.4 |
| `constraint_discovered` | Critical limitation found | 0.4 |
| `context_threshold` | Context usage exceeds 70% | 0.0 |
| `precompact` | Before `/compact` command | 0.0 |
| `manual` | User says "checkpoint" | 0.0 |

**Priority ordering:** topic_shift > branch_point > constraint > synthesis

### Manual Checkpoints

Say "checkpoint" or "save this" anytime to trigger a manual save.

### Checkpoint Contents

Each checkpoint captures:

- **Core question** — What decision is this driving toward?
- **Thesis** — Current synthesized position
- **Confidence** — How confident (0.0-1.0)
- **Key evidence** — Concrete facts/data points supporting the thesis (context hydration)
- **Reasoning trace** — Narrative explaining the thinking process (context hydration)
- **Open questions** — What's still unknown
- **Sources** — Decision-relevant summaries with relations (supports/contradicts/nuances)
- **Tensions** — Where credible sources disagree
- **Unique contributions** — Discoveries, experiments, synthesis
- **Action context** — Goal and type (decision/implementation/learning/exploration)
- **Metadata** — Skill, project, parent checkpoint, message count, token estimate

### Context Hydration

The `key_evidence` and `reasoning_trace` fields help Claude reconstruct its mental state when restoring from a checkpoint:

- **key_evidence**: List of concrete facts, data points, or observations that support the thesis
- **reasoning_trace**: Narrative prose explaining the thinking process that led to conclusions

These fields improve checkpoint restore quality by providing not just *what* was concluded, but *why*.

### Checkpoint Deduplication

When embeddings are available, Sage checks thesis similarity against recent checkpoints:
- Default threshold: 90% similarity
- Skips saving if too similar to recent checkpoint
- Configurable via `dedup_threshold` in tuning.yaml

### Depth Threshold Enforcement

Prevents shallow/noisy checkpoints by requiring minimum conversation depth:
- **depth_min_messages**: Minimum messages before checkpoint allowed (default: 8)
- **depth_min_tokens**: Minimum tokens before checkpoint allowed (default: 2000)

**Exempt triggers** (bypass depth check):
- `manual` — User explicitly requested
- `precompact` — Before compaction (critical)
- `context_threshold` — At 70% context usage
- `research_start` — Initial state capture

Callers that don't provide `message_count`/`token_estimate` (zero values) skip the check for backward compatibility.

### Project-Local Checkpoints

Create `.sage/` directory in a project to store checkpoints locally:

```bash
cd my-project
mkdir .sage
# Now checkpoints save to my-project/.sage/checkpoints/
```

### Storage Format

Checkpoints are **Markdown with YAML frontmatter** (Obsidian-compatible):

```markdown
---
id: 2026-01-16T12-00-00_checkpoint-name
type: checkpoint
ts: '2026-01-16T12:00:00Z'
trigger: synthesis
confidence: 0.85
skill: my-skill
project: my-project
message_count: 15
token_estimate: 6000
---

# Core Question Here

## Thesis
The synthesized position...

## Key Evidence
- Concrete fact 1 supporting the thesis
- Data point from research

## Reasoning Trace
Started by evaluating options A and B. Eliminated A due to constraint X.
B emerged as the better choice after considering factors Y and Z.

## Open Questions
- Question 1
- Question 2

## Sources
- **source-id** (type): Take — _relation_

## Tensions
- **src1** vs **src2**: Nature — _resolution_

## Unique Contributions
- **type**: Content
```

### Checkpoint Templates

Customize checkpoint format with templates.

**Built-in Templates:**

| Template | Purpose |
|----------|---------|
| `default` | Standard checkpoint with all fields |
| `research` | Research-focused with sources emphasis |
| `decision` | Decision-focused with options/tradeoffs |
| `code-review` | Code review with files/changes |

**Using Templates:**

```python
# Via MCP
sage_save_checkpoint(
    core_question="...",
    thesis="...",
    confidence=0.8,
    template="decision"  # Use decision template
)
```

**CLI Commands:**

```bash
sage templates list           # List available templates
sage templates show default   # Show template contents
```

**Custom Templates:**

Create `~/.sage/templates/my-template.yaml`:

```yaml
name: my-template
description: Custom template for X
required_fields:
  - core_question
  - thesis
optional_fields:
  - custom_field
format: |
  # {{ core_question }}

  ## Thesis
  {{ thesis }}

  {% if custom_field %}
  ## Custom Section
  {{ custom_field }}
  {% endif %}
```

Templates use Jinja2 sandboxed environment for security.

---

## Knowledge System

### Knowledge Types

Knowledge items have a `type` field that affects recall behavior:

| Type | Purpose | Recall Threshold |
|------|---------|------------------|
| `knowledge` | General facts (default) | 0.70 |
| `preference` | User preferences ("I prefer...") | 0.30 (aggressive) |
| `todo` | Persistent reminders | 0.40 |
| `reference` | On-demand reference material | 0.80 (conservative) |

**Saving with Type:**

```bash
# CLI
sage knowledge add prefs.md --id my-prefs --keywords style --type preference

# MCP
sage_save_knowledge(
    knowledge_id="my-prefs",
    content="I prefer functional style",
    keywords=["style"],
    item_type="preference"
)
```

**Todo Management:**

```bash
sage todo list              # List all todos
sage todo pending           # List pending todos
sage todo done <id>         # Mark todo as done
```

### Storing Knowledge

Save facts with keyword triggers:

```bash
# Via CLI
sage knowledge add content.md --id my-knowledge --keywords keyword1,keyword2

# Via MCP (Claude)
sage_save_knowledge(
    knowledge_id="my-knowledge",
    content="The content to store",
    keywords=["keyword1", "keyword2"]
)
```

### Automatic Recall

Knowledge is automatically injected when queries match keywords:

```
User: What do we know about GDPR consent?
Claude: [Auto-recalls matching knowledge]
        [Responds with context]
```

### Hybrid Scoring

When embeddings are available, knowledge is scored using:
- **70% semantic similarity** — Embedding cosine similarity
- **30% keyword matching** — Exact and substring matches

Configurable via `embedding_weight` and `keyword_weight` in tuning.yaml.

### Knowledge Scoping

Knowledge can be scoped to specific skills:

```bash
sage knowledge add content.md --id my-knowledge --keywords kw1 --skill my-skill
```

Scoped knowledge only recalls when that skill is active.

### Storage Format

Knowledge items are **Markdown with YAML frontmatter**:

```markdown
---
id: my-knowledge
type: knowledge
keywords:
- keyword1
- keyword2
source: Where this came from
added: '2026-01-16'
skill: my-skill  # Optional
---

## Actual Content

The knowledge content here...
```

---

## Configuration

### Config Files

| File | Location | Purpose |
|------|----------|---------|
| `tuning.yaml` | `~/.sage/` or `.sage/` | Tunable thresholds |
| `config.yaml` | `~/.sage/` | API key, model settings |

### Config Cascade

Resolution order (highest priority first):
1. Project-local `.sage/tuning.yaml`
2. User-level `~/.sage/tuning.yaml`
3. Built-in defaults

### Tunable Parameters

```yaml
# ~/.sage/tuning.yaml or .sage/tuning.yaml

# Retrieval thresholds
recall_threshold: 0.70       # Knowledge recall sensitivity (0-1)
dedup_threshold: 0.90        # Checkpoint deduplication threshold
embedding_weight: 0.70       # Weight for semantic similarity (0-1)
keyword_weight: 0.30         # Weight for keyword matching (0-1)

# Structural detection thresholds
topic_drift_threshold: 0.50  # Topic similarity threshold for drift
convergence_question_drop: 0.20  # Question ratio drop for synthesis
trigger_threshold: 0.60      # Combined 70/30 score for triggering
depth_min_messages: 8        # Min messages for depth checkpoint
depth_min_tokens: 2000       # Min tokens for depth checkpoint

# Embedding model (BGE-large for better retrieval)
embedding_model: BAAI/bge-large-en-v1.5
```

---

## Embeddings

### Default Model

- **Model:** `BAAI/bge-large-en-v1.5`
- **Dimensions:** 1024 (vs 384 for MiniLM)
- **Size:** ~1.3GB (downloaded on first use)
- **MTEB Score:** 63.0 (+7 points over MiniLM)
- **Runs locally on CPU**

### First Load Warning

On first use, Sage displays a download warning:
```
⚠️  Downloading embedding model (1340MB)... this only happens once.
```

### Query Prefix Support

BGE models perform better with query prefixes. Sage automatically:
- Adds prefix for search queries (`get_query_embedding`)
- Skips prefix for document storage (`get_embedding`)

### Model Mismatch Detection

When you change `embedding_model` in config:
- Sage detects dimension mismatch on load
- Returns empty store to trigger rebuild
- Log warning: "Embedding model changed... Embeddings will be rebuilt."

### Configuring a Different Model

```yaml
# ~/.sage/tuning.yaml
embedding_model: BAAI/bge-base-en-v1.5  # 768 dims, 440MB
# or
embedding_model: all-MiniLM-L6-v2        # 384 dims, 80MB (lighter)
```

After changing, rebuild embeddings:
```bash
sage admin rebuild-embeddings
```

### Capabilities

- Semantic knowledge recall (vs keyword-only)
- Checkpoint thesis deduplication
- Hybrid scoring (semantic + keyword)
- Checkpoint search by similarity

---

## CLI Commands

### Checkpoint Commands

```bash
sage checkpoint list [--limit N] [--skill NAME] [--project PATH]
sage checkpoint show <id>
sage checkpoint rm <id>
```

### Knowledge Commands

```bash
sage knowledge list [--skill NAME]
sage knowledge add <file> --id <id> --keywords <kw1,kw2> [--skill NAME] [--type TYPE]
sage knowledge match "query"  # Test what would be recalled
sage knowledge rm <id>
# sage knowledge debug "query"  # Coming in v2.1 - debug retrieval scoring
```

### Todo Commands

```bash
sage todo list                # List all todos
sage todo pending             # List pending todos
sage todo done <id>           # Mark todo as done
```

### Template Commands

```bash
sage templates list           # List available templates
sage templates show <name>    # Show template contents
```

### Config Commands

```bash
sage config list                        # Show all settings
sage config set <key> <value>           # Set user-level value
sage config set <key> <value> --project # Set project-level value
sage config reset                       # Reset tuning to defaults
sage config reset --project             # Reset project tuning
```

### Admin Commands

```bash
sage admin rebuild-embeddings
sage status  # Check Sage state
sage usage   # Token/cost analytics
```

### MCP/Hooks Commands

```bash
sage mcp install    # Install MCP server
sage hooks install  # Install Claude Code hooks
```

---

## MCP Tools

Tools available to Claude via MCP protocol:

### Checkpoint Tools

| Tool | Parameters | Returns |
|------|------------|---------|
| `sage_save_checkpoint` | core_question, thesis, confidence, open_questions, sources, tensions, unique_contributions, action_goal, action_type, key_evidence, reasoning_trace, **template** | Confirmation |
| `sage_load_checkpoint` | checkpoint_id | Formatted context |
| `sage_list_checkpoints` | limit, skill | List of checkpoints |
| `sage_search_checkpoints` | query, limit | Ranked matches with similarity scores |
| `sage_autosave_check` | trigger_event, core_question, current_thesis, confidence, open_questions, sources, tensions, unique_contributions, key_evidence, reasoning_trace, message_count, token_estimate | Save result |

### Checkpoint Search

Find relevant past research before starting a new task:

```
sage_search_checkpoints("JWT authentication patterns")

→ Found 12 checkpoints. Top 5 matches:

1. **[89%]** 2026-01-15T12-00-00_jwt-refresh-tokens
   JWT with refresh tokens provides secure stateless authentication...
   _Confidence: 85% | synthesis_

2. **[72%]** 2026-01-10T09-30-00_oauth-comparison
   OAuth 2.0 vs session-based auth comparison...
   _Confidence: 80% | synthesis_

Use `sage_load_checkpoint(id)` to inject a checkpoint into context.
```

### Knowledge Tools

| Tool | Parameters | Returns |
|------|------------|---------|
| `sage_save_knowledge` | knowledge_id, content, keywords, skill, source, **item_type** | Confirmation |
| `sage_recall_knowledge` | query, skill | Formatted knowledge |
| `sage_list_knowledge` | skill | List of items |
| `sage_remove_knowledge` | knowledge_id | Confirmation |

---

## Structural Trigger Detection (v2.3)

Automatic detection of checkpoint-worthy moments via semantic analysis.

### 70/30 Hybrid Scoring

Triggers use the same scoring approach as knowledge recall:
- **70% structural** — Embedding-based detection (topic drift, convergence)
- **30% linguistic** — Pattern matching (keywords, phrases)

This weighting prevents noisy triggers from keywords alone.

### Structural Detection

| Signal | Method | What It Detects |
|--------|--------|-----------------|
| **Topic drift** | Cosine similarity vs recent centroid | Conversation changed subjects |
| **Convergence** | Question→statement ratio shift | Research phase ending, synthesis beginning |

**Topic Drift:**
- Computes centroid of last 5 message embeddings
- If current message similarity < threshold (default 0.50), drift detected
- High confidence (1 - similarity) on low similarity

**Convergence:**
- Tracks question ratio in early vs late conversation halves
- When early is >50% questions and late drops below threshold, synthesis detected

### Linguistic Detection

Pattern matching for explicit trigger phrases:

| Type | Example Patterns |
|------|------------------|
| **Topic shift** | "moving on to", "let's turn to", "changing topics" |
| **Branch point** | "two approaches", "alternatively", "trade-off" |
| **Constraint** | "won't work because", "blocked by", "showstopper" |
| **Synthesis** | "in conclusion", "putting this together", "TL;DR" |

Patterns inside code blocks, inline code, and quotes are filtered out.

### Configuration

```yaml
# ~/.sage/tuning.yaml
trigger_threshold: 0.60      # Combined score threshold (0-1)
topic_drift_threshold: 0.50  # Similarity threshold for drift
convergence_question_drop: 0.20  # Question ratio drop
```

### Usage

```python
from sage.triggers import TriggerDetector, TriggerType

detector = TriggerDetector()

# Feed messages as conversation progresses
result = detector.analyze("Let's move on to databases", "assistant")

if result.should_trigger:
    trigger = result.trigger
    print(f"Checkpoint: {trigger.type.value} ({trigger.confidence:.0%})")
    # → Checkpoint: topic_shift (75%)
```

---

## Hooks

### Available Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `post-response-semantic-detector.sh` | Stop | Detect synthesis, branch points, constraints, topic shifts |
| `post-response-context-check.sh` | Stop | Trigger checkpoint at 70% context |
| `pre-compact.sh` | PreCompact | Checkpoint before manual compact, approve auto-compact |

### Hook Behavior

**Semantic Detector:**
- Scans response for trigger patterns
- Respects cooldown (30s default)
- Skips if discussing hooks/meta topics
- Priority ordering prevents multiple triggers

**Context Check:**
- Reads token usage from transcript
- Blocks at configurable threshold (default 70%)
- Uses cooldown to prevent repeated triggers

**Pre-Compact:**
- Blocks manual `/compact` for checkpoint
- Approves automatic compaction (prevents deadlock)
- Uses proper `trigger` field detection

### Hook Configuration

Environment variables:
```bash
SAGE_CONTEXT_THRESHOLD=70      # Context % threshold
SAGE_CONTEXT_WINDOW=200000     # Context window size
SAGE_CONTEXT_COOLDOWN=60       # Cooldown seconds
```

---

## Session Continuity (v2.4)

Automatic context restoration after Claude Code compaction events.

### How It Works

1. **70% context hook** saves checkpoint (existing behavior)
2. **Watcher daemon** detects `isCompactSummary: true` in Claude Code JSONL transcript
3. **Watcher writes marker** pointing to most recent checkpoint
4. **First sage tool call** after compaction injects checkpoint context automatically

### Watcher Daemon

The watcher is a background daemon that monitors Claude Code transcripts:

```bash
sage watcher start    # Start watching for compaction
sage watcher stop     # Stop the watcher
sage watcher status   # Check if running
```

**What it watches:**
- Claude Code JSONL transcripts in `~/.claude/projects/`
- Detects `{"isCompactSummary": true, "message": {"content": "..."}}`
- Extracts compaction summary and writes continuity marker

### Continuity Injection

When compaction is detected:
1. Watcher finds most recent checkpoint
2. Writes marker to `~/.sage/continuity.json`
3. On next `sage_health()` or `sage_continuity_status()` call:
   - Marker is read and formatted
   - Checkpoint context is loaded
   - Context is prepended to response
   - Marker is cleared (one-time injection)

### CLI Commands

```bash
# Watcher management
sage watcher start              # Start daemon
sage watcher stop               # Stop daemon
sage watcher status             # Show status with log tail

# Continuity management
sage continuity status          # Show pending marker details
sage continuity clear [--force] # Clear pending marker
sage continuity mark [--reason] # Manually create marker (for testing)
```

### MCP Tools

| Tool | Purpose |
|------|---------|
| `sage_continuity_status()` | Check continuity state, inject if pending |
| `sage_health()` | Includes watcher status, injects if pending |

### Configuration

```yaml
# ~/.sage/tuning.yaml
continuity_enabled: true   # Enable context injection (default)
watcher_auto_start: false  # Auto-start on MCP init (opt-in)
```

### Security

- **Daemon runs as user's process** — no privilege escalation
- **PID file has 0o600 permissions** — only owner can read
- **Log file has 0o600 permissions** — only owner can read
- **Path validation** — symlinks outside expected directories are skipped
- **No code execution** — JSON parsed safely, only string content extracted
- **Line length limit** — 10MB max to prevent memory exhaustion

### Typical Flow

```
User: [researching something]
Claude: [saves checkpoint at 70% context]

[Context compacts automatically]

Claude: [calls sage_health()]
→ "═══ SESSION CONTINUITY ═══

   **Claude Code Compaction Summary:**
   User was researching Python async patterns for FastAPI services...

   **Last Checkpoint:**
   Core question: How to handle async database operations?
   Thesis: Use async connection pools with proper context managers...
   ═══════════════════════════

   Sage Health Check
   ─────────────────────────────────────────
   ✓ Version: v2.4.0 (latest)
   ..."
```

---

## Proactive Recall (v2.5)

Sage automatically injects relevant knowledge at session start based on project context.

### How It Works

1. **Project detection** — Sage identifies your project from:
   - Directory name
   - Git remote URL (extracts repo name)
   - `pyproject.toml` project name
   - `package.json` name field

2. **Knowledge matching** — Project signals are used as a query against stored knowledge with a lower threshold (0.4 vs 0.7 normal)

3. **Auto-injection** — Matching knowledge is injected on the first Sage tool call of the session

### Example

Working in a project called `payments-api`:

```
User: [opens Claude Code in payments-api directory]
User: "What MCP tools do we have?"

Claude: [calls sage_list_knowledge]
→ "═══ RECALLED KNOWLEDGE ═══
   *Based on project context: payments-api*

   **stripe-integration** (stripe, payments, api)
   Use Stripe PaymentIntents for one-time charges. Always handle
   webhook signature verification...

   **pci-compliance** (pci, payments, compliance)
   Never log full card numbers. Use tokenization...
   ═══════════════════════════

   Found 12 knowledge items..."
```

### Session Start Context

On first tool call, Sage injects both:
1. **Continuity context** — If compaction was detected
2. **Proactive recall** — Knowledge matching project context

This happens automatically on any Sage tool call (`sage_health`, `sage_version`, `sage_list_knowledge`, etc.).

### Configuration

Proactive recall uses a lower threshold than normal recall to be more inclusive:

```yaml
# Internal default
proactive_threshold: 0.4  # vs recall_threshold: 0.7
```

### What Gets Recalled

- Knowledge with keywords matching project signals
- Both global and skill-scoped knowledge
- Items ranked by hybrid score (semantic + keyword)

---

## Skills (v2.6)

Sage ships methodology as Claude Skills for progressive disclosure—skills load on-demand when context matches triggers.

### The Three Layers

```
┌────────────────────────────────────────────────┐
│  Skills (methodology)                          │
│  Teach Claude WHEN and HOW to checkpoint       │
│  Load on-demand when context matches           │
├────────────────────────────────────────────────┤
│  MCP Server (tools)                            │
│  Provides the checkpoint/knowledge TOOLS       │
│  Always available to Claude                    │
├────────────────────────────────────────────────┤
│  Storage                                       │
│  Markdown files in ~/.sage/ or .sage/          │
│  Obsidian-compatible format                    │
└────────────────────────────────────────────────┘
```

### Default Sage Skills

| Skill | Triggers | Purpose |
|-------|----------|---------|
| `sage-memory` | checkpoint, save knowledge, autosave | Background Task pattern for non-blocking saves |
| `sage-research` | research, synthesis, hypothesis | When and how to checkpoint during research |
| `sage-session` | session start, hello, new session | Session start ritual (call `sage_health()`) |

### Installation

```bash
sage skills install   # Install all Sage methodology skills
sage skills list      # Check installed skills
sage skills update    # Update to latest versions
sage skills show <name>  # View skill content
```

### How Skills Work

1. Skills live in `~/.claude/skills/sage/<skill-name>/SKILL.md`
2. Each skill has YAML frontmatter with `triggers` list
3. When conversation context matches triggers, Claude loads the skill
4. Skill content teaches Claude the methodology

### Skill Format

```markdown
---
name: sage-memory
description: Background save pattern for Sage operations
triggers: [checkpoint, save knowledge, autosave, persist]
author: sage
version: 1.0.0
---

# Sage Memory Operations

When saving to Sage, **always use a background Task**...
```

### Custom Skills

Create your own methodology skills:

```bash
mkdir -p ~/.claude/skills/my-skill
```

Create `SKILL.md`:

```markdown
---
name: my-skill
description: My custom methodology
triggers: [keyword1, keyword2]
---

# My Skill

Instructions for Claude...
```

---

## Security

### Safe Practices

- All YAML uses `yaml.safe_load()`
- Embeddings use `np.load(allow_pickle=False)`
- Path sanitization prevents directory traversal
- No `eval()`, `pickle.load()`, or `exec()`

### Path Safety

IDs are sanitized to prevent path traversal:
```python
# "../../.bashrc" → "bashrc"
safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")
```

See [Security Checklist](security-deserialization-checklist.md) for full details.

---

## Backward Compatibility

### Checkpoint Format

- New format: `.md` (Markdown + frontmatter)
- Legacy format: `.yaml` (still readable)
- Both formats supported for loading
- New checkpoints always save as `.md`

### Knowledge Format

- New: Content files have YAML frontmatter
- Legacy: Content without frontmatter still loads
- Frontmatter stripped when returning content
