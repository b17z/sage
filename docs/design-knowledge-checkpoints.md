# Knowledge Recall & Checkpoints Design

## Problem

Claude UI hits context limits fast during intense research sessions. When context fills up, you lose:
- Prior reasoning and conclusions
- Important facts discovered mid-session
- The ability to reference earlier work

Manus solves this with two features we want to replicate:
1. **Knowledge Recall** - Automatic injection of relevant knowledge snippets
2. **Checkpoints** - Saveable/restorable conversation snapshots

---

## Feature 1: Knowledge Recall

### What It Does

Automatically detects when a query relates to stored knowledge and injects relevant snippets into context. Shows user what was recalled (e.g., "Knowledge recalled (2)").

### Why It Matters

- Keeps specialized knowledge out of base context (saves tokens)
- Only loads what's relevant to the current query
- Accumulates learnings across sessions without bloating every request

### Directory Structure

```
~/.sage/knowledge/
├── index.yaml              # registry of all knowledge items
├── global/                 # always-available knowledge
│   ├── api-patterns.md
│   └── research-methods.md
└── skills/                 # skill-scoped knowledge
    ├── privacy/
    │   └── gdpr-summary.md
    └── market-research/
        └── competitor-analysis.md
```

### Knowledge Item Schema

**index.yaml:**
```yaml
version: 1
items:
  - id: gdpr-summary
    file: skills/privacy/gdpr-summary.md
    triggers:
      keywords: [gdpr, privacy, data protection, eu regulation, consent]
      patterns: ["user data", "personal information"]
    scope:
      skills: [privacy]        # only inject for these skills (optional)
      always: false            # if true, always inject regardless of query
    metadata:
      added: 2026-01-10
      source: "research session 2026-01-08"
      tokens: 450

  - id: api-patterns
    file: global/api-patterns.md
    triggers:
      keywords: [api, rest, graphql, endpoint]
    scope:
      skills: []               # empty = all skills
      always: false
    metadata:
      added: 2026-01-05
      tokens: 320
```

### Recall Algorithm

**With embeddings installed** (`pip install claude-sage[embeddings]`):
```python
def recall_knowledge(query: str, skill_name: str) -> list[KnowledgeItem]:
    """
    Returns knowledge items relevant to the query.
    
    1. Load index.yaml
    2. Filter by skill scope
    3. Score each item with combined scoring:
       - 70% embedding similarity (semantic)
       - 30% keyword matching (lexical)
    4. Return items with score > threshold (default: 2.0 on 0-10 scale)
    5. Cap at max_items (default: 3) to avoid context bloat
    """
```

**Without embeddings** (fallback):
```python
def recall_knowledge(query: str, skill_name: str) -> list[KnowledgeItem]:
    """
    Returns knowledge items relevant to the query.
    
    1. Load index.yaml
    2. Filter by skill scope
    3. Score each item by trigger matches:
       - keyword exact match: +3 points
       - keyword substring: +1 point  
       - pattern regex match: +2 points
    4. Return items with score > threshold (default: 2)
    5. Cap at max_items (default: 3) to avoid context bloat
    """
```

### Context Injection

Recalled knowledge is injected after the skill content but before the user query:

```
[SKILL.md content]
[Shared memory]

---
📚 Recalled Knowledge (2 items):

## gdpr-summary.md
[content]

## api-patterns.md  
[content]
---

[User query]
```

### CLI Integration

```bash
# Add knowledge from a file
sage knowledge add gdpr-notes.md --keywords "gdpr,privacy" --skill privacy

# Add knowledge interactively (extracts from last response)
sage knowledge extract privacy
# > Extracting key insights from last response...
# > Found 3 potential knowledge items. Add them? [y/n]

# List knowledge
sage knowledge list
sage knowledge list --skill privacy

# Show what would be recalled for a query
sage knowledge match "How does GDPR affect our API?"

# Remove knowledge
sage knowledge rm gdpr-summary
```

### Display During Query

When running `sage ask`, show what was recalled:

```
$ sage ask privacy "What consent mechanisms do we need?"

📚 Knowledge recalled (2)
   ├─ gdpr-summary (450 tokens)
   └─ consent-patterns (280 tokens)

[streaming response...]
```

---

## Feature 2: Checkpoints

### What It Does

Saves snapshots of conversation state at meaningful points. User can restore a checkpoint to continue from that point, or branch off in a new direction.

### Why It Matters

- **Resume work**: Pick up where you left off after context limit
- **Branch exploration**: Try different approaches from the same point
- **Recovery**: Go back if the conversation goes off-track
- **Audit trail**: See how conclusions were reached

### Directory Structure

```
~/.sage/skills/<name>/checkpoints/
├── 2026-01-10T16-30-00_market-intel.json
├── 2026-01-10T15-45-00_initial-research.json
└── 2026-01-10T14-20-00_problem-definition.json
```

### Checkpoint Schema

```python
@dataclass(frozen=True)
class Checkpoint:
    id: str                          # unique identifier
    ts: str                          # ISO timestamp
    description: str                 # "Added Market Intelligence analysis"
    
    # Conversation state
    messages: list[Message]          # full message history
    system_context: str              # skill + docs + shared memory at time of save
    
    # What was active
    knowledge_recalled: list[str]    # knowledge item IDs that were injected
    
    # Metrics
    context_tokens: int              # estimated token count
    message_count: int               # number of turns
    
    # Metadata
    skill: str                       # which skill this belongs to
    parent_checkpoint: str | None    # if branched from another checkpoint
```

### Auto-Description Generation

When saving a checkpoint, auto-generate description from:

1. **Last assistant response** - Summarize the conclusion/action
2. **Last user query** - What was asked
3. **Fallback** - "Checkpoint at turn {n}"

```python
def generate_checkpoint_description(messages: list[Message]) -> str:
    """Generate a short description from recent conversation."""
    last_assistant = [m for m in messages if m.role == "assistant"][-1]
    
    # Use Claude to summarize in <10 words
    # Or extract first sentence/heading
    # Or use simple heuristics
```

### Save Triggers

Checkpoints can be saved:

1. **Manual** - User explicitly saves (`sage checkpoint save`)
2. **Auto on threshold** - After N turns or M tokens
3. **Auto on milestone** - When assistant says "Here's the summary" / "In conclusion"

### CLI Integration

```bash
# Save checkpoint (in chat mode)
sage chat privacy
> [conversation...]
> /checkpoint "Finished competitor analysis"
✓ Saved checkpoint: 2026-01-10T16-30-00_finished-competitor-analysis

# Or from command line after ask
sage checkpoint save privacy --description "Initial market research"

# List checkpoints
sage checkpoint list privacy
CHECKPOINT                              TURNS  TOKENS  DESCRIPTION
2026-01-10T16-30-00_finished-compet...  12     8,420   Finished competitor analysis
2026-01-10T15-45-00_initial-research    6      4,100   Initial market research

# Restore and continue
sage checkpoint restore privacy 2026-01-10T15-45-00_initial-research
# Starts chat with that conversation history loaded

# Show checkpoint details
sage checkpoint show privacy 2026-01-10T16-30-00_finished-competitor-analysis

# Branch from checkpoint (restore but mark as branch)
sage checkpoint branch privacy 2026-01-10T15-45-00 --name "alternative-approach"

# Delete old checkpoints
sage checkpoint prune privacy --keep 5
```

### Restore Flow

```
$ sage checkpoint restore privacy 2026-01-10T15-45-00_initial-research

📂 Restoring checkpoint: Initial market research
   ├─ 6 messages (4,100 tokens)
   ├─ Knowledge: gdpr-summary, market-trends
   └─ Saved: 2026-01-10 15:45

Continuing conversation...

You: What about the Asian market?
```

---

## Feature 3: Chat Mode (Deprioritized)

> **Status:** Deprioritized. Claude Code + MCP + Hooks now provides the primary interface.
> `sage chat` remains a future option for non-Claude-Code users or alternative LLM backends.

The original design required chat mode for multi-turn checkpoint support:

```bash
sage chat privacy
```

### Chat Commands

```
/help              - Show commands
/checkpoint [desc] - Save checkpoint
/restore [id]      - Restore checkpoint  
/knowledge         - Show recalled knowledge
/context           - Show current context size
/clear             - Clear conversation (keeps skill context)
/export [file]     - Export conversation to markdown
/quit              - Exit chat
```

### Chat State

```python
@dataclass
class ChatSession:
    skill: str
    messages: list[Message]
    knowledge_recalled: list[str]
    start_time: str
    last_checkpoint: str | None
    
    # Running metrics
    total_tokens_in: int
    total_tokens_out: int
    total_cost: float
```

---

## Implementation Plan

### Phase 1: Knowledge Recall (Foundation)
- [ ] Create `~/.sage/knowledge/` structure
- [ ] Implement `knowledge.py` module (index, load, match)
- [ ] Add `sage knowledge add/list/rm` commands
- [ ] Integrate recall into `sage ask` flow
- [ ] Display "Knowledge recalled (N)" on query

### Phase 2: Chat Mode
- [ ] Add `sage chat` command with REPL
- [ ] Track message history in session
- [ ] Add `/` commands for chat control
- [ ] Show running token/cost metrics

### Phase 3: Checkpoints
- [ ] Create checkpoint schema and storage
- [ ] Add `sage checkpoint save/list/restore` commands
- [ ] Implement auto-description generation
- [ ] Add `/checkpoint` command in chat mode
- [ ] Implement checkpoint branching

### Phase 4: Polish
- [ ] Auto-checkpoint on token threshold
- [ ] Knowledge extraction from responses (`sage knowledge extract`)
- [ ] Checkpoint diffing (what changed between checkpoints)
- [ ] Export checkpoint to shareable format

---

## Open Questions

1. **Knowledge matching**: ~~Simple keyword matching vs. embeddings?~~
   - ✅ **Resolved**: Now supports both! Install `claude-sage[embeddings]` for semantic matching
   - Combined scoring: 70% embedding similarity + 30% keyword matching
   - Falls back to keyword-only when embeddings unavailable
   - Uses `all-MiniLM-L6-v2` model (~80MB, runs locally)

2. **Checkpoint storage**: JSON files vs. SQLite?
   - JSON is simple, human-readable, easy to backup
   - SQLite better for querying across many checkpoints
   - **Proposal**: Start with JSON, migrate if needed

3. **Auto-checkpoint triggers**: What thresholds?
   - Every N turns (5? 10?)
   - Every M tokens (5000? 10000?)
   - On specific phrases ("In summary", "Here's the plan")
   - **Proposal**: Make configurable, default to 10 turns or 8000 tokens

4. **Context compression**: When restoring, summarize old messages?
   - Full restore preserves everything but may hit limits
   - Summarized restore loses nuance but saves tokens
   - **Proposal**: Offer both options on restore

---

## Manus Insights (from direct testing)

Manus describes its own features:

### Checkpoints (per Manus)
> "Creates a versioned snapshot of your entire project at a specific point in time."
- Uses tool `webdev_save_checkpoint`
- Captures complete file state (code, config, assets)
- Each checkpoint gets unique version ID (like `1d47c61e`)
- Can rollback to any previous checkpoint
- Required before publish/deploy

### Knowledge Recall (per Manus)
> "Retrieves relevant context from previous conversations or project history."
- Maintains knowledge base of past interactions, decisions, project context
- Automatically retrieved when you start session or ask questions
- The "(1)" indicates count of items recalled
- What gets recalled:
  - Previous decisions you made
  - Technical context (stack, features)
  - Past issues and resolutions
  - Preferences and requirements

### Key Distinction
**Checkpoints save artifacts, Knowledge saves reasoning.**

For Manus (web builder): artifacts = files/code
For Sage (research): artifacts = conversation threads, conclusions, sources

This means Sage checkpoints should emphasize:
- Conversation history and reasoning chains
- Conclusions reached and why
- Sources discovered and their relevance
- Decision points ("we chose X over Y because...")

### Manus Checkpoint Details (from testing)

**Format:**
| Version ID | Description | Date |
|------------|-------------|------|
| 1d47c61e | Removed PDF download button | Jan 9, 2026 |
| c362d1d6 | Cleaned up site, updated APY | Jan 9, 2026 |

- IDs are 8-char hashes (git-style)
- Descriptions are action-oriented ("Fixed X", "Added Y")
- Has Management UI for history/rollback
- Comparison uses git diff under the hood

**Knowledge Recall:**
- Cannot manually trigger - purely automatic
- Workaround: Ask "What do you remember about [topic]?"
- Retrieval based on: project context, keywords in message, recent history

### Sage Checkpoint Diff (Research-Focused)

For research, comparing checkpoints should show reasoning changes, not file diffs:

```
$ sage checkpoint diff privacy abc123 def456

📊 Checkpoint Comparison: abc123 → def456

Added conclusions:
  + GDPR Article 6 requires explicit consent for AI training
  + Found 3 academic sources supporting opt-out model

Changed positions:
  ~ Previously: "unclear if legitimate interest applies"
  ~ Now: "legitimate interest likely insufficient per recent ECJ ruling"

New sources cited:
  + [ECJ Case C-252/21] - ruling on AI and consent
```

---

## References

- Manus knowledge module: Injects "knowledge events" into event stream
- Manus todo.md: File-based progress tracking that survives context limits
- AutoGPT memory: Vector DB for long-term recall
- Claude prompt caching: Reuse prefix to save costs (sage already uses this)
