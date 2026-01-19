# Sage Features

Complete reference for all Sage capabilities.

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

---

## Knowledge System

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
topic_drift_threshold: 0.50  # Topic change detection
convergence_question_drop: 0.20
depth_min_messages: 8        # Min messages for depth checkpoint
depth_min_tokens: 2000       # Min tokens for depth checkpoint

# Embedding model
embedding_model: all-MiniLM-L6-v2
```

---

## Embeddings

### Installation

```bash
pip install claude-sage[embeddings]  # ~2GB for model + torch
```

### Default Model

- **Model:** `all-MiniLM-L6-v2`
- **Size:** ~80MB
- **Runs locally on CPU**

### Capabilities When Installed

- Semantic knowledge recall (vs keyword-only)
- Checkpoint thesis deduplication
- Hybrid scoring (semantic + keyword)

### Graceful Fallback

Sage works without embeddings:
- Knowledge recall uses keyword matching only
- Checkpoint deduplication is skipped
- No errors, just reduced functionality

### Rebuilding Embeddings

```bash
sage admin rebuild-embeddings
```

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
sage knowledge add <file> --id <id> --keywords <kw1,kw2> [--skill NAME]
sage knowledge match "query"  # Test what would be recalled
sage knowledge rm <id>
# sage knowledge debug "query"  # Coming in v2.1 - debug retrieval scoring
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
| `sage_save_checkpoint` | core_question, thesis, confidence, open_questions, sources, tensions, unique_contributions, action_goal, action_type, key_evidence, reasoning_trace | Confirmation |
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
| `sage_save_knowledge` | knowledge_id, content, keywords, skill, source | Confirmation |
| `sage_recall_knowledge` | query, skill | Formatted knowledge |
| `sage_list_knowledge` | skill | List of items |
| `sage_remove_knowledge` | knowledge_id | Confirmation |

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

## Skills (Optional)

### Skill Definition

Skills are defined in `~/.claude/skills/<name>/SKILL.md`:

```markdown
---
name: my-skill
description: What this skill does
expertise: Domain expertise
---

System prompt content here...
```

### Skill Commands

```bash
sage list                    # List all skills
sage ask <skill> "<query>"   # One-shot query
sage context <skill>         # Show what a skill knows
sage history <skill>         # Query history
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
