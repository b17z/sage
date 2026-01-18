# Sage Memory Framework

**"Don't lose your thinking."**

-----

## Philosophy

**Context windows aren't the problem. Losing your thinking is the problem. Context windows are just where it happens.**

Sage doesn't fight the context limit. It accepts compaction as inevitable and builds the save system around it.

-----

## The Three Save Modes

*All three are first-class. The hierarchy is about cognitive load, not importance.*

### 1. Pre-compaction (Emergency Backup)

> The game crashed → at least you have a recent save

|Aspect            |Detail                                                       |
|------------------|-------------------------------------------------------------|
|**When**          |Context window hits 70% threshold                            |
|**User attention**|Zero — invisible, always on                                  |
|**Purpose**       |You shouldn't lose everything just because Claude hit a limit|
|**Priority**      |🔴 Non-negotiable foundation                                  |

### 2. Auto-detection at Inflection Points (Flow Protection)

> You're in the boss cutscene → you shouldn't have to pause to manually save

|Aspect            |Detail                                                            |
|------------------|------------------------------------------------------------------|
|**When**          |Synthesis moments, branch decisions, topic shifts                 |
|**User attention**|Zero — catches you mid-flow                                       |
|**Purpose**       |Deep research/thinking shouldn't be interrupted by save management|
|**Priority**      |🔴 Critical for the core experience                                |

### 3. Manual (Intentional Preservation)

> You just found a rare item → you *want* to save right now

|Aspect            |Detail                                                   |
|------------------|---------------------------------------------------------|
|**When**          |User says "checkpoint this" or "save this as knowledge"  |
|**User attention**|Deliberate — user recognizes "this moment matters"       |
|**Purpose**       |Sometimes you know better than the system what's valuable|
|**Priority**      |🟡 Important — must be frictionless when needed           |

### Why All Three Matter

|If missing…   |What breaks                                           |
|--------------|------------------------------------------------------|
|Pre-compaction|Catastrophic loss on context limits                   |
|Auto-detection|Flow interruption, cognitive overhead during deep work|
|Manual        |No way to intentionally preserve "aha" moments        |

**Critical path (all working ✅):**

1. Pre-compaction (foundation) — ✅ `pre-compact.sh` hook
1. Auto-detection (flow protection) — ✅ `post-response-semantic-detector.sh`
1. Manual (intentionality) — ✅ MCP tools (`sage_save_checkpoint`, `sage_autosave_check`)

-----

## Research → Code Spec Workflow

**This document is a research spec. Code spec skeleton is included below.**

The workflow:

```
Research Spec (this doc)        ✅ COMPLETE
    ↓ Validate assumptions      ✅ Done
    ↓ Get feedback              ✅ Done (multiple rounds)
    ↓ Iterate                   ✅ v2.4 final
    ↓
Code Spec (skeleton below)      ← YOU ARE HERE
    ↓ Interfaces, functions, types
    ↓ Test cases
    ↓
Implementation
```

Research is a big part of coding novel things in spaces you may not be an expert in yet. Doing research and coding simultaneously in Claude Code is a monstrous superpower — but the research phase clarifies *what* to build before *how* to build it.

-----

## What's Actually Novel

*Don't lose these differentiators in implementation.*

|Feature                              |Why It's Novel                                    |
|-------------------------------------|--------------------------------------------------|
|Auto-checkpoint at inflection points |Nothing else detects "meaningful moments"         |
|Bidirectional Claude ↔ knowledge sync|Active session, not just storage                  |
|Context restoration UX               |"Pick up where you left off" not "search my notes"|
|Pre-compaction saves                 |Automatic preservation before Claude loses it     |
|User-tunable retrieval               |Power users calibrate their own knowledge base    |

**Note:** Obsidian storage format is a **distribution strategy** (PKM community, graph view for free), not a differentiator. The Claude + Obsidian space is getting crowded (Claudesidian, obsidian-claude-code-mcp, mcp-obsidian). Don't compete on storage — compete on intelligence.

-----

## Current State vs Proposed

*Sage already exists and is shipping. This spec is about what's next.*

|Feature                   |Current State                                  |Spec Proposes                      |
|--------------------------|-----------------------------------------------|-----------------------------------|
|Embedding model           |MiniLM-L6-v2 (~80MB, 384 dim)                  |mxbai-embed-large (~670MB)         |
|Knowledge retrieval       |✅ Hybrid: 70% embedding + 30% keyword          |Asymmetric embedding (query prefix)|
|Checkpoint deduplication  |✅ 0.9 threshold, last 20 checkpoints           |— (already solid)                  |
|Knowledge recall threshold|✅ 0.7 similarity                               |Tuning based on mxbai              |
|Quote-stripping           |✅ Perl regex (code, quotes, blockquotes)       |— (done)                           |
|Cooldown                  |✅ 30 sec per trigger type                      |Content hashing (future)           |
|Meta-discussion ban       |✅ Prevents trigger loops                       |— (done)                           |
|Priority ordering         |✅ topic_shift > branch > constraint > synthesis|— (done)                           |
|Knowledge versioning      |None                                           |History array, freshness decay     |
|Todos                     |Not built                                      |Full primitive                     |
|Storage format            |YAML                                           |Markdown + frontmatter             |
|Checkpoint hydration      |Basic                                          |key_evidence + reasoning_trace     |
|Obsidian integration      |None                                           |Optional enhancement               |
|Cross-project knowledge   |Project OR global (no cascade)                 |Priority-based cascade             |
|Batch embedding rebuild   |✅ `rebuild_all_embeddings()`                   |— (ready for model swap)           |
|Retrieval tuning          |Hardcoded thresholds                           |User-configurable via `sage config`|

**Key finding from code review:** Implementation is more mature than README suggests. Hybrid retrieval, quote-stripping, and per-trigger cooldowns are all working.

-----

## Critical Issues & Mitigations

### 🔴 HIGH: Embedding Model Quality

**The problem:** MiniLM-L6-v2 trades accuracy for speed (~80MB). For a memory system where recall matters more than latency, that tradeoff may be wrong. Users have reported queries returning 0.68 similarity when threshold is 0.70 — knowledge silently doesn't surface.

**Current mitigation (already implemented):**

- Hybrid retrieval: 70% embedding + 30% keyword
- Keyword matches always included regardless of embedding score
- This is belt-and-suspenders — keyword guarantees recall, embedding enables discovery

```python
# From knowledge.py (ALREADY IMPLEMENTED)
EMBEDDING_WEIGHT = 0.7  # 70% embedding similarity
KEYWORD_WEIGHT = 0.3    # 30% keyword matching

def score_item_combined(...):
    combined = EMBEDDING_WEIGHT * embedding_similarity + KEYWORD_WEIGHT * keyword_normalized
    return combined * 10.0
```

**Upgrade target:** `mxbai-embed-large` from mixedbread.ai (~670MB, quantized available). One of the best open-source models on MTEB.

**Implementation note — asymmetric embedding (NOT yet implemented):**

```python
# mxbai requires query prefix for optimal retrieval
query_text = f"Represent this sentence for searching relevant passages: {query}"
query_embedding = model.encode(query_text)

# Documents get embedded without prefix
doc_embedding = model.encode(document_text)
```

**Migration path:**

1. Swap model in `embeddings.py` (`DEFAULT_MODEL = "mixedbread-ai/mxbai-embed-large-v1"`)
1. Add query prefix in `get_embedding()` when used for queries
1. Run `rebuild_all_embeddings()` to re-embed all knowledge/checkpoints
1. Tune thresholds (mxbai scores differently than MiniLM)

-----

### 🟢 NEW: Tuning Workflow (Power Users)

**The insight:** The spec originally treated `sage knowledge debug` as a diagnostic tool ("why didn't X surface?"). But it should be part of a **tuning workflow** where power users calibrate retrieval for their specific knowledge base.

**Why this matters:**

- Different knowledge bases cluster differently (research-heavy vs code-heavy)
- Different domains have different semantic properties
- The "right" threshold is empirical, not universal
- Power users who hit retrieval issues want agency, not just explanations

**The feedback loop:**

```
1. Query returns unexpected results (miss or noise)
2. `sage knowledge debug "query"` → see scores and thresholds
3. `sage config set recall_threshold 0.65` → adjust
4. `sage knowledge debug "query"` → verify fix
5. Repeat until dialed in
```

**Configurable parameters:**

```bash
# Retrieval tuning
sage config set recall_threshold 0.70      # When to surface knowledge
sage config set dedup_threshold 0.90       # When to skip redundant checkpoints
sage config set embedding_weight 0.70      # Weight for semantic similarity
sage config set keyword_weight 0.30        # Weight for keyword matching

# View current config
sage config list
# → recall_threshold: 0.70
# → dedup_threshold: 0.90
# → embedding_weight: 0.70
# → keyword_weight: 0.30
# → embedding_model: mixedbread-ai/mxbai-embed-large-v1

# Reset to defaults
sage config reset recall_threshold
sage config reset --all
```

**Enhanced debug output with config awareness:**

```bash
$ sage knowledge debug "morpho curator"

Query: "morpho curator"
Config: recall_threshold=0.70, embedding_weight=0.70, keyword_weight=0.30

Would retrieve (above 0.70):
  ✓ morpho-curator-economics    combined=0.847  (emb=0.82, kw=0.91)
  ✓ defi-yield-strategies       combined=0.723  (emb=0.71, kw=0.75)

Near misses (0.60 - 0.70):
  ✗ aave-lending-rates          combined=0.682  (emb=0.68, kw=0.70)
  ✗ compound-governance         combined=0.651  (emb=0.62, kw=0.72)

Tip: `sage config set recall_threshold 0.65` would include 2 more items
```

**The "Tip" line is key** — it tells you exactly what lever to pull. Debug isn't just showing you the problem; it's proposing the solution.

**Progressive disclosure:**

| User Type | What They See |
|-----------|---------------|
| Casual | Never touches config. Defaults work. |
| Power user hitting issues | `sage knowledge debug` → sees scores → adjusts threshold |
| Power user optimizing | `sage config list` → tweaks all parameters → verifies with debug |

**Config storage:**

```yaml
# ~/.sage/config.yaml
retrieval:
  recall_threshold: 0.70
  dedup_threshold: 0.90
  embedding_weight: 0.70
  keyword_weight: 0.30

embedding:
  model: "mixedbread-ai/mxbai-embed-large-v1"

# Project-level overrides (optional)
# <project>/.sage/config.yaml overrides user-level
```

**Project-level config:**

Different projects might need different tuning:

```bash
# In a research project (wants broad recall)
cd ~/morpho-research
sage config set recall_threshold 0.60 --project

# In a code project (wants precise recall)
cd ~/sage
sage config set recall_threshold 0.75 --project
```

-----

#### Trigger Signal Hierarchy (Noise Reduction)

**The problem:** Linguistic patterns alone are too noisy. Single keywords like "option" trigger on throwaway phrases.

```
User: "I don't have any other option but to..."
       ↑ Would trigger branch_point — but it's not a real decision point
```

**The fix:** Structural signals *initiate*, linguistic signals *confirm*.

| Signal Combination | Action | Rationale |
|--------------------|--------|-----------|
| High-confidence structural (>0.8) | ✅ Trigger | Clear inflection point |
| Linguistic only | ❌ No trigger | Too noisy alone |
| Structural + linguistic | ✅ Trigger (even at 0.5) | Confirmation boosts confidence |
| Neither | ❌ No trigger | Nothing detected |

**Implementation:**

```python
def should_trigger(
    structural: Trigger | None,
    linguistic: Trigger | None
) -> Trigger | None:
    """
    Structural signals initiate triggers.
    Linguistic signals confirm but don't initiate.
    """
    # High-confidence structural alone = trigger
    if structural and structural.confidence > 0.8:
        return structural

    # Linguistic alone = NOT enough (too noisy)
    if linguistic and not structural:
        return None  # Reject — keywords alone are unreliable

    # Structural + linguistic = trigger with boosted confidence
    if structural and linguistic:
        if structural.confidence > 0.5:
            return Trigger(
                type=structural.type,
                confidence=min(0.95, structural.confidence + 0.2),  # Boost
                source="structural+linguistic",
                reason=f"{structural.reason}; confirmed by '{linguistic.reason}'"
            )

    return None
```

**Why this matters:**

- **New users:** Structural catches their inflection points without false positives
- **Power users:** Their explicit language boosts confidence, doesn't create noise
- **Everyone:** Fewer garbage checkpoints cluttering history

**Keyword pattern guidelines:**

| Pattern Type | Use For | Noise Level |
|--------------|---------|-------------|
| Single words ("option") | ❌ Never as sole trigger | 🔴 Very high |
| Short phrases ("let me think") | ⚠️ Confirmation only | 🟡 Medium |
| Long phrases ("let me think through the options") | ✅ Confirmation | 🟢 Low |
| Structural + any keyword | ✅ Trigger | 🟢 Very low |

---

#### Implementation Roadmap

| Version | Feature | Work Required | Impact |
|---------|---------|---------------|--------|
| **v2.1** | Topic drift detection (embedding similarity) | Medium — rolling window embeddings | High — catches topic shifts for everyone |
| **v2.1** | Convergence detection (question → statement ratio) | Low — regex counting | Medium — catches synthesis moments |
| **v2.1** | Claude behavior detection | Low — pattern match on responses | Medium — leverages Claude's own signals |
| **v2.1** | Depth thresholds (min messages/tokens) | Low — counting + config | Low — prevents shallow checkpoints |
| **v2.2** | Configurable structural thresholds | Low — extend `sage config` | Medium — power user tuning |
| **v2.2** | User-customizable linguistic patterns | Low — config file | Medium — personal vocabulary |
| **v2.3** | Checkpoint load/delete tracking | Medium — feedback loop storage | Foundation for adaptive |
| **v2.3** | Threshold adjustment from feedback | Medium — hit rate analysis | Medium — learns what user values |
| **v2.4** | Personal pattern extraction | High — n-gram mining | High — truly personalized triggers |
| **Future** | Cross-user pattern sharing | High — privacy considerations | Medium — bootstraps new users |

---

#### The Cold Start Solution

**The key insight:** Structural signals work for everyone on day one. No learning required, no vocabulary to master.

| User State | What Works | Detection Mix |
|------------|------------|---------------|
| **Day 1** (new user) | Topic drift, Claude synthesis behavior, depth thresholds | 100% structural |
| **Week 1** (getting familiar) | Above + starts using checkpoint language naturally | 70% structural, 30% linguistic |
| **Month 1** (regular user) | Above + system learns their patterns | 50% structural, 30% linguistic, 20% adaptive |
| **Month 3+** (power user) | Full personalization, custom patterns | 40% structural, 30% linguistic, 30% adaptive |

**What this means in practice:**

```
New user, day 1:
- Talks normally, doesn't know "checkpoint language"
- Structural detection catches topic shift via embeddings
- Checkpoint created automatically
- User: "Whoa, it saved my thinking without me asking"

Power user, month 3:
- Has developed personal phrases ("ok let me marinate on this")
- Adaptive has learned this phrase precedes valuable checkpoints
- Triggers even without matching default patterns
- User: "Sage knows exactly when I'm having an insight"
```

**The progressive experience:**

1. **Just works** — New users get checkpointed via structural signals
2. **Gets better** — System observes which checkpoints matter
3. **Feels personal** — Eventually triggers feel intuitive, not mechanical

---

### ✅ IMPLEMENTED: Semantic Detection & Quote-Stripping

**From `post-response-semantic-detector.sh` (code review Jan 2026):**

**Quote-stripping (prevents false triggers):**

```bash
msg_stripped=$(echo "$msg_lower" | perl -0777 -pe '
    s/```.*?```//gs;           # Remove fenced code blocks
    s/`[^`]+`//g;              # Remove inline code
    s/"[^"]*"//g;              # Remove double-quoted strings
    s/^>.*$//gm;               # Remove blockquotes
')
```

**Meta-discussion ban list (prevents trigger loops):**

```bash
if echo "$msg_lower" | grep -qE "(hook|checkpoint|trigger|pattern|detector|cooldown|sage_autosave).*(fire|detect|block|test)|test.*summary|trigger.*loop"
```

**Priority ordering (most actionable first):**

1. `topic_shift` — Context change, checkpoint before losing previous
1. `branch_point` — Decision point, capture options before choosing
1. `constraint_discovered` — Blocker found, important pivot
1. `synthesis` — Catch-all for conclusions (lowest priority)

**Cooldown mechanism:**

- 30 seconds per trigger type (not 5 minutes as old docs said)
- Configurable via `SAGE_SEMANTIC_COOLDOWN` env var
- Stored in `~/.sage/cooldown/` (not `/tmp` — avoids symlink attacks)
- Per-trigger-type tracking (synthesis cooldown doesn't block branch_point)

-----

### 🔴 HIGH: Freshness Decay Creates Matthew Effect

**The problem:** If recall boosts freshness, popular items stay fresh while niche items rot — even if the niche item is exactly what you need for a rare query.

```
Popular item recalled → freshness boosted → ranks higher → recalled more
Niche item not recalled → decays → ranks lower → recalled less → decays faster
```

**The fix:** Separate ranking signals from archival signals.

```python
# RANKING: Affects retrieval order (what surfaces first)
def rank_score(item: Knowledge, query_embedding: Embedding) -> float:
    return (
        cosine_similarity(query_embedding, item.embedding) * 0.6 +
        recency_score(item.updated_at) * 0.25 +
        recall_frequency_score(item.recall_count) * 0.15
    )

# FRESHNESS: Affects archival (what gets pruned)
def freshness(item: Knowledge) -> float:
    # Based on UPDATE time, NOT recall time
    days_since_update = (now() - item.updated_at).days
    return 0.5 ** (days_since_update / 90)  # Halves every 90 days
```

**Key insight:** Recall frequency is a **ranking signal** (frequently-recalled items are probably important). But it shouldn't prevent archival of items that haven't been *updated* — otherwise you create a popularity contest where niche-but-valuable items rot.

**Freshness should decay based on staleness of content, not frequency of access.**

-----

### 🟡 MEDIUM: Cross-Project Knowledge Portability

**The problem:** Knowledge scoped to projects may be silently unavailable when you need it elsewhere.

**Solution:** Cross-project search with priority ordering.

```python
def retrieve_knowledge(query: str, project: Project | None) -> list[Knowledge]:
    results = []

    # Priority 1: Project-scoped (if in a project)
    if project:
        project_matches = search(query, scope=project)
        results.extend([(item, priority=1.0) for item in project_matches])

    # Priority 2: User-global (always searched)
    global_matches = search(query, scope="user")
    results.extend([(item, priority=0.8) for item in global_matches])

    return dedupe_and_rank(results)
```

**UX:** When knowledge from another project surfaces, note it:

```
Claude: "From your morpho-research project: Curator fees are $12-15M/quarter..."
```

-----

### 🟡 MEDIUM: "Just Works" vs Power User Tension

**The problem:** Onboarding promises magic ("Just works!") but spec has complex admin commands. Risk: two half-products.

**Solution:** Aggressive progressive disclosure with namespaced commands.

**Casual user surface (default `sage help`):**

```bash
sage status              # Am I okay?
sage search <query>      # Find stuff
sage load <query>        # Restore context
sage checkpoint          # Manual save
```

**Power user surface (`sage admin help`):**

```bash
sage admin prune --stale
sage admin budget set 20000
sage admin freshness threshold 0.3
sage config set embedding_model "..."
sage knowledge debug <query>
```

**Progressive status output:**

```bash
# Casual mode (default)
$ sage status
🌿 Sage: 3 checkpoints, 12 knowledge items. All healthy.

# Verbose mode
$ sage status --verbose
🌿 Sage Status
─────────────────────────────────────
Checkpoints:     3 (last: 2h ago, synthesis trigger)
Knowledge:       12 active, 2 archived
Token budget:    12,847 / 15,000 (85%)
Freshness:       2 items below threshold (0.35, 0.28)

Recent activity:
  • [14:30] Checkpoint: morpho-curator-analysis
  • [14:25] Knowledge recalled: defi-yield-basics
  • [14:20] Auto-save triggered (synthesis detected)

Run `sage admin prune --dry-run` to review stale items.
```

-----

## YAML → Markdown Migration

**Migration script:**

```python
def migrate_checkpoint(yaml_path: Path) -> str:
    """Convert YAML checkpoint to Markdown + frontmatter."""
    data = yaml.safe_load(yaml_path.read_text())

    frontmatter = {
        "id": data["id"],
        "type": "checkpoint",
        "timestamp": data["timestamp"],
        "trigger": data.get("trigger", "unknown"),
        "confidence": data.get("confidence", 0.5),
    }

    body = f"""# {data.get('title', 'Checkpoint')}

## Core Question
{data.get('core_question', 'N/A')}

## Thesis
{data.get('thesis', 'N/A')}

## Key Evidence
{format_list(data.get('key_evidence', []))}

## Reasoning Trace
{data.get('reasoning_trace', 'N/A')}

## Open Questions
{format_list(data.get('open_questions', []))}
"""

    return f"---\n{yaml.dump(frontmatter)}---\n\n{body}"
```

One-time transform. No dual-write needed.

## First-Run Experience

**Problem:** Someone installs Sage — then what? First impressions matter for CLI tools.

**Proposed onboarding:**

```bash
> pip install claude-sage[embeddings]
> sage init

╭─────────────────────────────────────────╮
│                                         │
│   🌿 Welcome to Sage                    │
│                                         │
│   Don't lose your thinking.             │
│                                         │
╰─────────────────────────────────────────╯

Sage gives Claude persistent memory:

  📍 Checkpoints save where you ARE
     (Like game saves — restore exact state)

  🧠 Knowledge saves what you KNOW
     (Facts and conclusions that evolve)

  ✅ Todos save what to DO
     (Action items that persist)

All three survive context compaction.

Setup complete. Sage will:
  • Auto-checkpoint at synthesis moments
  • Save knowledge when you learn something durable
  • Restore context in new sessions

Project initialized: ~/.sage/

Type `sage help` for commands.
Type `sage status` to see what's saved.

Ready when you are.
```

**Post-init, in Claude Code:**

```
Claude: "Sage is active. I'll checkpoint automatically at
         inflection points and before compaction.

         Say 'checkpoint this' anytime to save manually.
         Say 'what do we know about X' to recall knowledge.

         Let's get started."
```

**Progressive disclosure:**

- First session: Just works (auto-checkpoint, auto-recall)
- Power users discover: `sage help`, manual commands, config
- Teams discover: `sage project init`, collaboration features

-----

## Core Concepts

Sage has two types of memory, each serving a distinct purpose:

|                     |**Checkpoints**              |**Knowledge**              |
|---------------------|-----------------------------|---------------------------|
|**Analogy**          |Game save states             |Player skill/wisdom        |
|**Question answered**|"Where was I?"               |"What do I know?"          |
|**Nature**           |Temporal snapshots           |Evolving understanding     |
|**Mutability**       |Immutable (historical record)|Mutable (updates over time)|
|**Scope**            |Session-specific state       |Cross-session wisdom       |

-----

## Checkpoints: Save States

### What They Are

Checkpoints are **point-in-time snapshots** of your working state. Like a game save, they capture everything needed to resume from that exact moment.

### When They're Created

- **Inflection points** — Synthesis moments, branch decisions, topic shifts
- **Pre-compaction** — Automatic save before context loss
- **Explicit** — User/Claude says "checkpoint this"

### What They Contain

```yaml
checkpoint:
  id: 2026-01-13T14-30-00_morpho-analysis
  timestamp: 2026-01-13T14:30:00Z
  trigger: synthesis  # or: precompact, explicit, branch_point, topic_shift

  # The state at this moment
  core_question: "What's the fee structure for Morpho curators?"
  thesis: "Top curators earn $3-4M/quarter, but concentration risk is high"
  confidence: 0.75

  # WHY you reached this conclusion (critical for hydration)
  key_evidence:
    - "Dune query 6255951: Steakhouse at $1.5M last quarter"
    - "Fee structure is % of yield, averaging 0.15%"
    - "Top 2 curators control 68% of TVL"
  reasoning_trace: |
    Started with total market size from Dune dashboard.
    Broke down by curator, noticed Steakhouse dominance.
    Concentration pattern raised sustainability questions.
    Cross-referenced with Gauntlet's public reports.

  # What was in progress
  open_questions:
    - "How sustainable are these fees as TVL grows?"
    - "What's Gauntlet's strategy vs Steakhouse?"

  # What informed the state
  sources:
    - id: dune-query-6255951
      relation: supports
    - id: steakhouse-docs
      relation: primary

  # Unresolved tensions
  tensions:
    - "Fee sustainability vs TVL competition pressure"

  # Token tracking (for budget management)
  token_count: 287  # Estimated tokens when loaded
```

**Note on `key_evidence` and `reasoning_trace`:** These fields are critical for context hydration. Without them, checkpoints capture *what* you concluded but not *why*. The reasoning trace helps Claude reconstruct the mental state, not just read the conclusion.

### How They're Used

**Restore session state:**

```
User: "Load my Morpho research checkpoint"
Claude: *loads checkpoint*
Claude: "Resuming from Jan 13. You were analyzing curator fees.
         Your thesis was that top curators earn $3-4M/quarter.
         Open questions: fee sustainability, Gauntlet vs Steakhouse strategy.
         Where do you want to pick up?"
```

### Key Properties

- **Immutable** — Once saved, never changed. It's history.
- **Stackable** — Multiple checkpoints form a timeline of thinking
- **Complete** — Everything needed to resume, in one object
- **Auditable** — You can trace how your thinking evolved

-----

## Knowledge: Evolving Understanding

### What It Is

Knowledge represents **what you've learned** — conclusions, facts, and synthesis that persist and evolve across sessions.

### When It's Created

- **Post-synthesis** — After reaching a conclusion worth remembering
- **Factual discovery** — Learning something concrete and reusable
- **Cross-checkpoint patterns** — Insights that span multiple sessions

### What It Contains

```yaml
knowledge:
  id: morpho-curator-economics
  created: 2026-01-10
  updated: 2026-01-13

  # Current understanding
  content: |
    Morpho curator fees: ~$12-15M/quarter total market.
    Top curators: Steakhouse (#1, ~$1.5B AUM), Gauntlet (#2, ~$700M).
    Fee structure: % of yield, varies by vault.
    Key insight: Concentration risk — top 2 curators control majority.

  # For retrieval
  keywords: [morpho, curator, fees, defi, yield]

  # Provenance
  sources:
    - dune-query-6255951
    - checkpoint: 2026-01-13T14-30-00_morpho-analysis

  # Evolution history
  history:
    - date: 2026-01-10
      content: "Morpho curator fees: ~$12M/quarter..."
      reason: "Initial research"
    - date: 2026-01-13
      content: "Morpho curator fees: ~$12-15M/quarter..."
      reason: "Updated with Q1 2026 data"
```

### How It's Used

**Inform any session:**

```
User: "What do I know about DeFi yield strategies?"
Claude: *recalls knowledge*
Claude: "Based on your research: Morpho curators earn $12-15M/quarter,
         top 2 control majority of AUM. You noted concentration risk
         as a key concern. [Last updated: Jan 13]"
```

### Key Properties

- **Mutable** — Updates as understanding deepens
- **Versioned** — History preserved, evolution tracked
- **Cross-session** — Applies anywhere, not tied to one context
- **Retrievable** — Semantic search surfaces relevant knowledge

-----

## The Relationship

```
Sessions produce → Checkpoints (save states)
                        ↓
              Checkpoints inform → Knowledge (synthesis)
                        ↓
              Knowledge informs → Future sessions
                        ↓
              Future sessions → New checkpoints
                        ↓
                    (cycle continues)
```

### Example Flow

**Session 1: Initial Research**

```
- Research Morpho curators
- Checkpoint: "Initial findings, fees ~$12M/quarter"
- Save knowledge: morpho-curator-economics (v1)
```

**Session 2: Deeper Analysis**

```
- Load checkpoint from Session 1
- Recall knowledge: morpho-curator-economics
- New data: fees now $15M/quarter
- Checkpoint: "Updated analysis with Q1 data"
- Update knowledge: morpho-curator-economics (v2)
```

**Session 3: Related Research**

```
- Researching DeFi yield strategies (different topic)
- Recall knowledge: morpho-curator-economics (surfaces as relevant)
- Use existing knowledge to inform new research
- Checkpoint: "Yield strategy comparison"
- New knowledge: defi-yield-comparison
```

-----

## Decision Framework

**Should this be a checkpoint or knowledge?**

```
                    Is this a moment in time?
                              │
              ┌───────────────┴───────────────┐
              ↓                               ↓
             YES                              NO
              │                               │
              ↓                               ↓
    "Where I was at this moment"    "What I concluded/learned"
              │                               │
              ↓                               ↓
         CHECKPOINT                       KNOWLEDGE


Examples:                           Examples:
- "Thesis as of today: X"           - "Morpho fees are $15M/quarter"
- "Open questions right now"        - "Curators have concentration risk"
- "State before compaction"         - "Pattern: fees scale with AUM"
- "Branch point: chose A over B"    - "Key contact: @steaborhood"
```

-----

## Practical Guidelines

### Checkpointing

**Good checkpoint triggers:**

- Synthesis moment ("putting this together…")
- Branch decision ("going with approach A")
- Topic shift (starting new thread of research)
- Pre-compaction (automatic, always save)
- Explicit request ("checkpoint this")

**Checkpoint frequency:**

- Too frequent = noise, redundant snapshots
- Too sparse = lost state, gaps in timeline
- Right balance = meaningful inflection points only

**Deduplication:**

- Same thesis (>0.90 similarity) = skip
- Thesis evolved meaningfully = save

### Knowledge Management

**Good knowledge items:**

- Concrete facts with sources
- Conclusions you'd want to recall later
- Patterns observed across sessions
- Key data points (numbers, dates, IDs)

**When to update vs create new:**

- Same topic, new data → Update existing
- Same topic, contradictory data → Update with note
- Related but distinct topic → Create new
- Completely new domain → Create new

**Knowledge hygiene:**

- Include sources (for verification)
- Date updates (for freshness)
- Keep concise (for token efficiency)

-----

## The Trinity (Future)

```
Checkpoints = Where your thinking IS (state)
Knowledge   = What you KNOW (understanding)
Todos       = What you need to DO (action)
```

All three persist. All three survive compaction. All three restore context.

Together they answer:

- Where was I? (checkpoint)
- What do I know? (knowledge)
- What's next? (todos)

-----

## Tagline

**Sage: Don't lose your thinking.**

- Checkpoints preserve where you were
- Knowledge preserves what you learned
- Together, they preserve your thinking

-----

## Open Questions & Design Decisions

*Feedback from real usage and review*

### 1. Retrieval Strategy

**Problem:** "Semantic search surfaces relevant knowledge" is doing heavy lifting. With 200 knowledge items, how do you decide what's relevant?

**Current approach:**

```
Query → Embed → Top-k by similarity → Threshold filter → Return
Scoring: 70% embedding + 30% keyword hybrid
```

**Open questions:**

- What's the right k? (5? 10? Dynamic?)
- What threshold cuts off noise without losing signal?
- Should recent items rank higher than old ones?
- Should frequently-recalled items rank higher?

**Potential enhancements:**

- Relevance ranking (not just similarity)
- Query expansion (include related terms)
- Context-aware retrieval (what are we working on?)

**Resolution: User-tunable thresholds (v2.4)**

Rather than picking "the right" threshold, make it configurable. Different knowledge bases cluster differently. Power users can calibrate for their domain.

-----

### 2. Token Budgeting

**Problem:** 50 checkpoints + 100 knowledge items can't all load into context. How does Sage decide what to pull in?

**The meta-problem:** This is the same context limit problem, pushed one level up.

**Hard numbers:**

|Item                                             |Tokens          |
|-------------------------------------------------|----------------|
|Claude Code context window                       |~200,000        |
|Typical session usage (files, conversation, code)|~100,000-150,000|
|Available for memory                             |~50,000-100,000 |
|Safe memory budget (conservative)                |~15,000-20,000  |
|Checkpoint (with key_evidence)                   |~300-500        |
|Knowledge item                                   |~100-300        |
|**Max items at safe budget**                     |**~40-60 items**|

**Implementation:**

```python
def load_context(budget_tokens: int = 15000) -> LoadResult:
    """
    Load memory items within token budget.

    Priority order:
    1. Pinned items (non-negotiable)
    2. Project-scoped items (sorted by recency)
    3. Global items (if budget remains)

    Returns what was loaded and what was skipped.
    """
    loaded = []
    skipped = []
    remaining_budget = budget_tokens

    for tier in [pinned_items, project_items, global_items]:
        for item in sorted(tier, key=lambda x: x.updated_at, reverse=True):
            if item.token_count <= remaining_budget:
                loaded.append(item)
                remaining_budget -= item.token_count
            else:
                skipped.append(item)

    return LoadResult(
        loaded=loaded,
        skipped=skipped,
        budget_used=budget_tokens - remaining_budget,
        budget_remaining=remaining_budget
    )
```

**When budget is exhausted:**

|Option            |Decision                                     |
|------------------|---------------------------------------------|
|Silently skip     |❌ Bad UX, user doesn't know                  |
|Warn user         |✅ "Loaded 45 items, 12 skipped due to budget"|
|Offer to load more|✅ "Say 'load more context' to expand"        |
|Summarize skipped |🟡 Maybe v2 — complexity                      |

**Graceful degradation message:**

```
Sage: "Context loaded (12,847 / 15,000 tokens)
       ✓ 3 checkpoints, 8 knowledge items
       ⚠ 5 older items skipped (budget)

       Say 'load [item]' to pull in specific items."
```

**Design decision needed:** Default strategy + user overrides?

-----

### 3. Knowledge Conflicts

**Problem:** "Update with note" when data contradicts — but what if new data is wrong? What if old data was wrong? Who arbitrates?

**Proposed approach:** Human in the loop — but only for active conflicts.

```
Claude: "Conflict detected.
         Existing: Morpho fees $12M/quarter (source: Dune Oct 2025)
         New data: Morpho fees $15M/quarter (source: Dune Jan 2026)

         Options:
         1. Update (replace old with new)
         2. Keep both (note discrepancy)
         3. Discard new (keep existing)

         Which?"
```

**The scaling problem:** Human-in-the-loop doesn't scale to 100+ knowledge items over months. Users will ignore prompts, leading to knowledge rot.

**Solution: Confidence Decay**

Knowledge items have a `freshness` score that degrades over time:

```yaml
knowledge:
  id: morpho-curator-economics
  created: 2026-01-10
  updated: 2026-01-13
  last_recalled: 2026-01-13
  freshness: 0.95  # Decays over time, affects retrieval priority
```

**Decay function:**

```python
def calculate_freshness(item: Knowledge) -> float:
    days_since_update = (now() - item.updated).days
    days_since_recall = (now() - item.last_recalled).days

    # Base decay: halves every 90 days
    base_freshness = 0.5 ** (days_since_update / 90)

    # Recall boost: recent recall resets decay
    recall_boost = 0.3 * (0.5 ** (days_since_recall / 30))

    return min(1.0, base_freshness + recall_boost)
```

**Freshness affects behavior:**

|Freshness|Behavior                                    |
|---------|--------------------------------------------|
|> 0.7    |Normal retrieval priority                   |
|0.3 - 0.7|Lower priority, retrieved if relevant       |
|< 0.3    |Auto-archive candidate, excluded from recall|

**Auto-archive prompt (monthly):**

```
Sage: "5 knowledge items haven't been recalled in 60+ days:
       - defi-yield-basics (last: Nov 2025)
       - morpho-v1-analysis (last: Oct 2025)
       ...

       Archive these? [y/n/review]"
```

**Open questions:**

- Should Claude auto-resolve if source is newer + same authority?
- How to handle conflicting sources of equal weight?
- Should conflicts be flagged for later review?

-----

### 4. Checkpoint Selection

**Problem:** "Load my Morpho research checkpoint" — what if there are 5 Morpho checkpoints?

**Search dimensions:**

- **Semantic:** Query matches thesis content
- **Temporal:** Recency (last 5, this week, etc.)
- **Explicit:** By ID or tag
- **Scoped:** Project-local first, then global

**UX options:**

```
# Semantic search
> sage load "morpho curator fees"
Found 3 checkpoints:
  1. [Jan 13] "Curator fee sustainability analysis" (0.89)
  2. [Jan 10] "Initial Morpho research" (0.76)
  3. [Dec 28] "DeFi yield comparison" (0.52)
Load which? [1/2/3/all]

# Recency
> sage load --recent 3
Loads last 3 checkpoints

# Explicit
> sage load 2026-01-13T14-30-00_morpho-analysis
```

**Design decision needed:** Default behavior when ambiguous?

-----

### 5. Knowledge Bloat

**Problem:** Knowledge accumulates. Stale items clutter recall. What's the archival/cleanup story?

**Staleness indicators:**

- Not recalled in N days (30? 60? 90?)
- Not updated in N days
- Low relevance scores when recalled
- Superseded by newer knowledge

**Proposed tiers:**

```
Active    → Auto-recalled, counts toward token budget
Archived  → Not auto-recalled, searchable explicitly
Deleted   → Gone (with grace period?)
```

**Maintenance commands:**

```bash
sage prune --stale          # Archive items not recalled in 30 days
sage prune --dry-run        # Show what would be archived
sage knowledge archive <id> # Manual archive
sage knowledge restore <id> # Unarchive
```

**Open question:** Auto-archive or always manual?

-----

### 6. The Todos Gap

**Problem:** State + Understanding without Action is incomplete.

**The trinity:**

```
Checkpoints = Where you ARE    (state)     ✅ Built
Knowledge   = What you KNOW    (wisdom)    ✅ Built
Todos       = What to DO       (action)    ❌ Missing
```

**Why it matters:**

- Claude Code's native todos don't persist across sessions
- Open questions in checkpoints are implicit todos
- Action items get lost in compaction

**Proposed schema:**

```yaml
todo:
  id: todo-001
  content: "Verify Gauntlet fee structure"
  priority: high | medium | low
  status: pending | in_progress | done | blocked
  source: checkpoint-2026-01-13  # Where it came from
  due: 2026-01-15  # Optional
  context: "Need for curator comparison analysis"
```

**Commands:**

```bash
sage todo add "Verify Gauntlet fees" --priority high
sage todo list --status pending
sage todo done <id>
```

**The prompt fatigue problem:**

If you prompt "Convert open_questions to todos?" after every checkpoint, users develop fatigue and just hit 'n'.

**Solution: Surface at session start, not checkpoint time.**

```
Claude: "Welcome back. Last session you had 3 open questions:

         1. How sustainable are these fees as TVL grows?
         2. What's Gauntlet's strategy vs Steakhouse?
         3. Should we look at MEV extraction?

         Any of these still relevant? [1/2/3/all/none]"
```

This is natural — you're picking up where you left off and triaging. It doesn't interrupt flow mid-session.

**Open question:** ~Should todos auto-extract from checkpoint open_questions?~
**Decision:** Suggest at session start, not during checkpointing.

-----

### 7. Projects / Scopes

**Problem:** "Scope-based" retrieval mentioned but no first-class Project primitive. Everything is effectively global.

**Current state (after David's PR):**

```
~/.sage/                    # Global
<project>/.sage/            # Project-local (if .sage dir exists)
```

Storage is scoped. But retrieval isn't project-aware yet.

**Proposed Project primitive:**

```yaml
project:
  id: morpho-research
  name: "Morpho Curator Analysis"
  root: /Users/ben/code/morpho-analysis
  created: 2026-01-10

  # What belongs to this project
  checkpoints: [...]  # Project-scoped
  knowledge: [...]    # Project-scoped
  todos: [...]        # Project-scoped

  # Pinned items (always load)
  pinned:
    knowledge: [morpho-curator-economics, defi-yield-basics]
    checkpoints: []

  # Collaborators (for team features)
  collaborators:
    - user: dmichael
      role: contributor
```

**Scope hierarchy for retrieval:**

```
1. Project-scoped (highest priority)
2. User-scoped (your stuff across projects)
3. Global-scoped (shared/pinned)
```

**Session startup:**

```
> claude
Sage: "Detected project: morpho-research
       Last checkpoint: Jan 13, 'Curator fee analysis'
       3 pending todos
       Load project context? [y/n]"
```

**Commands:**

```bash
sage project init              # Create .sage/ in current dir
sage project info              # Show current project
sage project pin <knowledge>   # Pin to always load
sage project switch <name>     # Change active project
```

**Open questions:**

- Should projects auto-detect from .sage or require explicit init?
- Cross-project knowledge sharing? (Some knowledge is universal)
- Project templates? (Common setups for research vs code vs etc.)

-----

### 8. Storage Format: YAML vs Markdown (Obsidian Integration)

**Problem:** YAML is machine-readable but not human-friendly. Building pruning, graph visualization, search, and sync is reinventing wheels that already exist.

**Insight:** If checkpoints and knowledge are **Markdown with frontmatter**, they become compatible with the entire PKM (Personal Knowledge Management) ecosystem — especially Obsidian.

**Proposed format:**

```markdown
---
id: morpho-curator-economics
type: knowledge
created: 2026-01-10
updated: 2026-01-13
keywords: [morpho, curator, fees, defi]
sources:
  - dune-query-6255951
  - "[[checkpoint-2026-01-13-morpho-analysis]]"
status: active  # or: archived, stale
---

# Morpho Curator Economics

$12-15M/quarter total market. Top curators: Steakhouse (#1), Gauntlet (#2).

Key insight: Concentration risk — top 2 control majority.

## History
- 2026-01-13: Updated with Q1 data
- 2026-01-10: Initial research
```

**What Obsidian gives you for free:**

|Feature         |Sage builds it|Obsidian has it              |
|----------------|--------------|-----------------------------|
|Pruning/archival|`sage prune`  |Move to Archive folder       |
|Graph view      |Build it      |Built-in, gorgeous           |
|Backlinks       |Build it      |Automatic `[[wikilinks]]`    |
|Search          |Embeddings    |Full-text + tags + properties|
|Sync            |Build it      |Obsidian Sync / git          |
|Mobile access   |Build it      |Obsidian Mobile              |
|Daily notes     |Build it      |Core plugin                  |
|Templates       |Build it      |Core plugin                  |

**Sage's role becomes:**

```
┌─────────────────────────────────────────────────┐
│  Claude Code                                    │
│  (Conversation, research, synthesis)            │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  Sage                                           │
│  (Hooks, triggers, checkpoint creation,         │
│   semantic detection, MCP tools)                │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  Obsidian Vault                                 │
│  (Storage, visualization, graph, search,        │
│   sync, mobile, PKM ecosystem)                  │
└─────────────────────────────────────────────────┘
```

**Sage = Claude → Obsidian bridge**

**Directory structure:**

```
~/Obsidian/Sage/              # or ~/.sage/ with Obsidian pointed at it
├── checkpoints/
│   ├── 2026-01-13-morpho-analysis.md
│   └── 2026-01-10-initial-research.md
├── knowledge/
│   ├── morpho-curator-economics.md
│   └── defi-yield-basics.md
├── todos/
│   └── pending.md            # or individual files
└── projects/
    └── morpho-research/
        └── ...
```

**Wikilink connections:**

```markdown
# In a checkpoint
Sources: [[knowledge/morpho-curator-economics]]
Related: [[checkpoints/2026-01-10-initial-research]]

# In knowledge
Derived from: [[checkpoints/2026-01-13-morpho-analysis]]
```

Obsidian's graph view automatically visualizes the connections between your thinking.

**Implementation options:**

|Option          |Pros                |Cons            |
|----------------|--------------------|----------------|
|Markdown only   |Full Obsidian compat|Parsing overhead|
|YAML only       |Fast, simple        |No PKM ecosystem|
|Both (export)   |Best of both        |Sync complexity |
|Markdown primary|Obsidian-first      |Slightly slower |

**Recommendation:** Markdown with frontmatter as primary format. The PKM ecosystem is massive — Obsidian, Logseq, Foam, Dendron all use this format. Sage becomes interoperable with all of them.

**⚠️ Source of Truth (Critical):**

> **"Obsidian files are authoritative. Sage re-indexes on session start. Edit in Obsidian anytime — Sage will pick up changes next session."**

This resolves the dual-source problem:

- User edits in Obsidian → Sage sees it next session
- Sage writes are atomic (full file replacement, not patches)
- No merge conflicts, no sync complexity
- Clear mental model for users

**Critical: Obsidian is optional, not required**

Vanilla Sage must work without Obsidian. The markdown files are just files — Obsidian enhances them but isn't needed.

```bash
# Standalone mode (default)
sage init
# Creates ~/.sage/ with markdown files
# Works fine, no Obsidian needed

# Obsidian mode (opt-in)
sage init --obsidian ~/Obsidian/Sage
# Points Sage at an Obsidian vault
# Same markdown files, but now Obsidian features light up
```

**What you get in each mode:**

|Feature            |Standalone    |With Obsidian                   |
|-------------------|--------------|--------------------------------|
|Checkpoints        |✅             |✅                               |
|Knowledge          |✅             |✅                               |
|Todos              |✅             |✅                               |
|Semantic search    |✅ (embeddings)|✅ (embeddings + Obsidian search)|
|Graph visualization|❌             |✅                               |
|Backlink navigation|❌             |✅                               |
|Mobile access      |❌             |✅                               |
|Sync               |Manual        |Obsidian Sync / git             |
|Community plugins  |❌             |✅ (Dataview, etc.)              |

**The pitch:**

- **New users:** `sage init` just works
- **PKM users:** `sage init --obsidian` unlocks the ecosystem

**The PKM crowd:**

Personal Knowledge Management is a whole movement — people obsessive about "second brain" systems, note-taking workflows, and knowledge graphs. Tools: Obsidian, Roam, Logseq, Notion.

They will love this. "AI that writes to my Obsidian vault" is a dream for that community.

-----

## Knowledge Extraction Workflow

**The problem:** The spec shows a nice diagram:

```
Sessions → Checkpoints → Knowledge → Future Sessions
```

But the *extraction* workflow is hand-wavy. When a checkpoint is created, how does knowledge get extracted from it?

**Applying the three-mode framing:**

|Approach |Description                                       |Assessment                       |
|---------|--------------------------------------------------|---------------------------------|
|Manual   |User says "save this as knowledge"                |✅ Essential — must work perfectly|
|Prompted |After checkpoint, Claude asks "Save as knowledge?"|⚠️ Prompt fatigue risk            |
|Automatic|Claude extracts during checkpointing              |🔮 Future polish                  |
|Post-hoc |Periodic review of checkpoints                    |🔮 Future polish                  |

**Manual knowledge saves are like manual checkpoints** — "I just found something rare, I want to save this specifically." Must be frictionless.

**Auto-extraction is like auto-checkpoint** — flow protection, catches things you'd forget to save. Nice to have but not critical for v2.

**Recommendation:**

1. **Now:** Make manual knowledge saves instant and obvious ("remember this", "save as knowledge")
1. **Later:** Add auto-extraction as polish once the core is solid

**Detection patterns for future auto-extraction:**

```python
KNOWLEDGE_PATTERNS = {
    # Concrete facts with numbers
    "quantitative": r"\$?\d+[MBK]?(?:/quarter|/year|%|bps)?",

    # Named entities worth remembering
    "entities": ["is the", "are the", "works at", "founded by"],

    # Conclusions/discoveries
    "conclusions": ["the key insight is", "importantly", "notably", "discovered that"],

    # Constraints/requirements
    "constraints": ["must be", "requires", "cannot", "only works if"],
}
```

This is future work — manual knowledge saving is the priority.

-----

## Design Decisions Made

*Based on feedback, discussion, and code review*

|Question                  |Decision                                      |Rationale                                           |
|--------------------------|----------------------------------------------|----------------------------------------------------|
|Hybrid retrieval          |✅ 70% embedding + 30% keyword                 |Already implemented in `knowledge.py`               |
|Quote-stripping           |✅ Perl regex                                  |Handles code blocks, inline code, quotes, blockquotes|
|Cooldown mechanism        |✅ 30s per trigger type                        |Secure paths (`~/.sage/cooldown/`), env-configurable|
|Meta-discussion ban       |✅ Regex ban list                              |Prevents trigger loops                              |
|Deduplication threshold   |✅ 0.9 similarity                              |Last 20 checkpoints checked                         |
|Knowledge recall threshold|✅ 0.7 similarity                              |Tunable in `embeddings.py`                          |
|Priority ordering         |✅ topic > branch > constraint > synthesis     |Most actionable first                               |
|Asymmetric embedding      |Separate `get_query_embedding()` function     |Explicit at call site, avoids boolean soup          |
|Threshold tuning          |User-configurable via `sage config`           |Different domains need different thresholds         |
|`sage knowledge debug`    |Build for v2.0 with tuning suggestions        |Cheap, high-value for trust + user agency           |
|Token budgeting strategy  |Scope + recency hybrid                        |Project scopes retrieval, recency breaks ties       |
|Token budget default      |15,000 tokens                                 |Conservative, leaves room for work                  |
|Budget exhaustion         |Warn + offer to load more                     |Transparency over silent skipping                   |
|Auto-archive              |Manual first, freshness decay                 |Build intuition before automating                   |
|Knowledge decay           |Freshness based on UPDATE time, not recall    |Prevents Matthew effect — ranking ≠ archival        |
|Todos from open_questions |Suggest at session START                      |Avoids prompt fatigue mid-session                   |
|Conflict resolution       |Human in the loop                             |Auto-resolve is a trap                              |
|Project detection         |Auto-detect .sage, explicit init              |Low friction, but controllable                      |
|Cross-project search      |Priority cascade (project → global, 0.8 boost)|Intuitive, no cognitive overhead                    |
|Storage format            |Markdown + frontmatter                        |PKM ecosystem compatibility                         |
|Obsidian integration      |Optional, v2.2                                |Core value is save system, not storage              |
|Obsidian source of truth  |Obsidian files are authoritative              |Sage re-indexes on session start                    |
|Checkpoint schema         |Include key_evidence + reasoning_trace        |Critical for context hydration                      |
|Embedding model upgrade   |mxbai-embed-large                             |Better semantic quality, rebuild script ready       |

-----

## Implementation Priority

Given the three-mode framing (pre-compaction + auto-detection + manual):

|Phase     |Feature                            |Rationale                                      |
|----------|-----------------------------------|-----------------------------------------------|
|✅ **Done**|Hybrid retrieval (70/30)           |Already implemented in `knowledge.py`          |
|✅ **Done**|Quote-stripping                    |Perl regex in semantic detector                |
|✅ **Done**|Per-trigger cooldown               |30s, secure paths, configurable                |
|✅ **Done**|Meta-discussion ban                |Prevents trigger loops                         |
|✅ **Done**|Checkpoint deduplication           |0.9 threshold, embedding-based                 |
|✅ **Done**|Batch embedding rebuild            |`rebuild_all_embeddings()` ready for model swap|
|**v2.0**  |mxbai-embed-large upgrade          |Better semantic quality                        |
|**v2.0**  |Asymmetric embedding (query prefix)|Required for mxbai optimal performance         |
|**v2.0**  |key_evidence in checkpoints        |Better context hydration on restore            |
|**v2.0**  |`sage knowledge debug` command     |Transparency for retrieval misses              |
|**v2.0**  |`sage config` for threshold tuning |User agency over retrieval parameters          |
|**v2.0**  |README.md overhaul                 |Currently stale, misleading users              |
|**v2.0**  |docs/ARCHITECTURE.md               |System design documentation                    |
|**v2.0**  |docs/ROADMAP.md                    |Feature timeline and versioning                |
|**v2.0**  |docs/FEATURES.md                   |User-facing feature documentation              |
|**v2.1**  |Separate ranking from archival     |Prevents Matthew effect in knowledge           |
|**v2.1**  |Cross-project knowledge search     |Priority cascade (project → global)            |
|**v2.1**  |Structural trigger detection       |Topic drift, convergence, Claude behavior      |
|**v2.1**  |Depth thresholds for checkpoints   |Prevents shallow/noisy checkpoints             |
|**v2.2**  |Markdown + frontmatter format      |Obsidian compatibility                         |
|**v2.2**  |Progressive disclosure CLI         |Better UX for both personas                    |
|**v2.2**  |Configurable structural thresholds |Power user tuning for triggers                 |
|**v2.3**  |Todos primitive                    |Completes trinity                              |
|**v2.3**  |Freshness decay implementation     |Prevents knowledge rot                         |
|**v2.3**  |Checkpoint feedback tracking       |Foundation for adaptive learning               |
|**v2.4**  |Adaptive trigger learning          |Personalized detection from usage patterns     |
|**Future**|Auto knowledge extraction          |Polish — manual works, auto is gravy           |
|**Future**|Content-hash cooldown              |Smarter than time-based                        |
|**Future**|Cross-user pattern sharing         |Bootstrap new users from community patterns    |

**Critical path (all working ✅):**

1. Pre-compaction (foundation) — ✅ `pre-compact.sh` hook
1. Auto-detection (flow protection) — ✅ `post-response-semantic-detector.sh`
1. Manual (intentionality) — ✅ MCP tools (`sage_save_checkpoint`, `sage_autosave_check`)

-----

## Risk Matrix

|Issue                         |Severity  |Status              |Mitigation                                                          |
|------------------------------|----------|--------------------|--------------------------------------------------------------------|
|Pre-compaction hook           |🔴 Critical|✅ Working           |Non-negotiable foundation — protect at all costs                    |
|Auto-detection accuracy       |🔴 Critical|✅ Working           |Quote-stripping, meta-ban, priority ordering all implemented        |
|Semantic trigger cold start   |🟡 Medium  |✅ Decision made     |Structural detection (v2.1) works for new users without training    |
|Semantic retrieval misses     |🟡 Medium  |✅ Mitigated         |Hybrid retrieval (70/30) + user-tunable thresholds                  |
|Quote-stripping               |🟢 Done    |✅ Implemented       |Perl regex handles code blocks, inline code, quotes, blockquotes    |
|Cooldown mechanism            |🟢 Done    |✅ Implemented       |30s per trigger type, secure paths, env-configurable                |
|Meta-discussion loops         |🟢 Done    |✅ Implemented       |Ban list prevents trigger-on-trigger-discussion                     |
|Freshness decay Matthew effect|🟡 Medium  |✅ Decision made     |Ranking ≠ archival (v2.1)                                           |
|Cross-project knowledge       |🟡 Medium  |✅ Decision made     |Priority cascade: project → global (v2.1)                           |
|Context hydration             |🟡 Medium  |v2.0                |key_evidence + reasoning_trace                                      |
|Token budget                  |🟡 Medium  |Needs implementation|Hard limits + graceful degradation                                  |
|Documentation stale           |🟡 Medium  |v2.0                |README overhaul, ARCHITECTURE.md, ROADMAP.md, FEATURES.md           |
|Knowledge extraction workflow |🟢 Low     |Manual is fine      |Auto-extraction is future polish                                    |
|YAML → Markdown migration     |🟢 Low     |v2.2                |One-time transform                                                  |

-----

## Open Questions — Resolved

*All decisions made during final spec review (Jan 15-16, 2026)*

|Question                  |Decision                                    |Rationale                                                             |
|--------------------------|--------------------------------------------|----------------------------------------------------------------------|
|**Asymmetric embedding**  |Separate function: `get_query_embedding()`  |Avoids boolean soup, explicit at call site, grep-able                 |
|**Threshold tuning**      |User-configurable via `sage config`         |Different domains cluster differently — power users should tune       |
|**`sage knowledge debug`**|Build for v2.0 with tuning suggestions      |Shows scores + suggests threshold adjustments                         |
|**Obsidian priority**     |Keep at v2.2                                |Core value is save system, not storage format                         |
|**Freshness decay**       |Ranking ≠ archival                          |Recall frequency → ranking boost; Update staleness → archive candidate|
|**Cross-project search**  |Priority cascade (project → global)         |Intuitive mental model, no cognitive overhead                         |

-----

## Code Spec Skeleton (v2.0)

*Ready to move to implementation phase*

```markdown
# Sage v2.0 Code Spec

## Scope
- mxbai-embed-large integration
- Asymmetric embedding (query prefix)
- key_evidence in checkpoint schema
- Threshold recalibration (user-tunable)
- `sage knowledge debug` command with tuning suggestions
- `sage config` command for parameter management
- Documentation overhaul

## Files to Modify

### embeddings.py
- [ ] Change DEFAULT_MODEL to "mixedbread-ai/mxbai-embed-large-v1"
- [ ] Add `get_query_embedding()` function with prefix
- [ ] Load thresholds from config (not hardcoded)
- [ ] Update RECALL_THRESHOLD default after calibration
- [ ] Update DEDUP_THRESHOLD default after calibration

### knowledge.py
- [ ] Update `_get_all_embedding_similarities()` to use `get_query_embedding()`
- [ ] Load embedding_weight and keyword_weight from config
- [ ] Add `debug` CLI command with enhanced output
- [ ] Add tuning suggestion ("Tip: `sage config set...`")

### config.py (NEW)
- [ ] Create Config dataclass with defaults
- [ ] Load from ~/.sage/config.yaml
- [ ] Project-level override support (<project>/.sage/config.yaml)
- [ ] CLI: `sage config list`
- [ ] CLI: `sage config set <key> <value> [--project]`
- [ ] CLI: `sage config reset <key> [--all]`
- [ ] Validation for threshold ranges (0.0-1.0)

### checkpoint.py
- [ ] Add key_evidence field to Checkpoint dataclass
- [ ] Add reasoning_trace field to Checkpoint dataclass
- [ ] Update save_checkpoint() to handle new fields
- [ ] Update format_checkpoint_for_context() to display new fields

### mcp_server.py
- [ ] Update sage_save_checkpoint() params to include key_evidence
- [ ] Update sage_autosave_check() to accept key_evidence

## New Commands

### sage config
```bash
sage config list                              # Show all config
sage config set recall_threshold 0.65         # Set user-level
sage config set recall_threshold 0.65 --project  # Set project-level
sage config reset recall_threshold            # Reset to default
sage config reset --all                       # Reset all to defaults
```

### sage knowledge debug (enhanced)
```bash
sage knowledge debug "morpho curator"
# Output:
# Query: "morpho curator"
# Config: recall_threshold=0.70, embedding_weight=0.70, keyword_weight=0.30
#
# Would retrieve (above 0.70):
#   ✓ morpho-curator-economics    combined=0.847  (emb=0.82, kw=0.91)
#
# Near misses (0.60 - 0.70):
#   ✗ aave-lending-rates          combined=0.682  (emb=0.68, kw=0.70)
#
# Tip: `sage config set recall_threshold 0.65` would include 1 more item
```

## Documentation Updates

### README.md (overhaul — currently stale)
- [ ] Update "What Works" section to reflect actual implementation
- [ ] Document hybrid retrieval (70/30 split)
- [ ] Document quote-stripping (implemented)
- [ ] Fix cooldown time (30s, not 5min)
- [ ] Add embedding model info (MiniLM now, mxbai upgrade path)
- [ ] Update "Known Limitations" — many are now resolved
- [ ] Add "v2.0 Upgrade" section for mxbai migration
- [ ] Document `sage config` for power users

### docs/ARCHITECTURE.md (new)
- [ ] System overview diagram (hooks → MCP → storage)
- [ ] Data flow: checkpoint creation, knowledge recall
- [ ] File structure: ~/.sage/, embeddings, checkpoints, knowledge
- [ ] Hook lifecycle: PreCompact, Stop (semantic detector)
- [ ] Embedding pipeline: model, storage (.npy + .json), similarity
- [ ] Hybrid retrieval algorithm (70% embedding + 30% keyword)
- [ ] Deduplication flow (thesis embedding → cosine similarity → threshold)
- [ ] Config loading hierarchy (defaults → user → project)

### docs/ROADMAP.md (new)
- [ ] v1.x (current): What's shipped and working
- [ ] v2.0: mxbai upgrade, key_evidence, debug command, config tuning
- [ ] v2.1: Freshness decay, cross-project search
- [ ] v2.2: Markdown + Obsidian integration
- [ ] v2.3: Todos primitive
- [ ] Future: Auto knowledge extraction, content-hash cooldown

### docs/FEATURES.md (new)
- [ ] Three save modes explained (pre-compaction, auto-detection, manual)
- [ ] Semantic detection patterns and priority ordering
- [ ] Knowledge system (save, recall, hybrid retrieval)
- [ ] Checkpoint schema and hydration
- [ ] CLI reference (casual vs admin commands)
- [ ] Configuration options (env vars, thresholds, `sage config`)
- [ ] Tuning workflow for power users

## Test Cases
- [ ] Embedding model swap doesn't break existing data
- [ ] Query prefix applied correctly (queries only, not documents)
- [ ] Recall threshold behaves similarly post-calibration
- [ ] Dedup threshold behaves similarly post-calibration
- [ ] Debug command shows expected output format
- [ ] Debug command shows tuning suggestion when near-misses exist
- [ ] Config set/get/reset work correctly
- [ ] Project-level config overrides user-level
- [ ] key_evidence populated on new checkpoints
- [ ] key_evidence displayed on checkpoint load
- [ ] Old checkpoints (without key_evidence) load gracefully

## Migration
- [ ] Script: `sage admin rebuild-embeddings`
- [ ] Threshold calibration script (one-time dev task)
- [ ] No schema migration needed (new fields optional)
- [ ] Config file created on first `sage config` command
```

-----

*Framework v2.5 (FINAL) — January 16, 2026*

**Status: Ready for code spec phase**

*Research spec complete. All open questions resolved. Code spec skeleton included. Tuning workflow added. Semantic trigger roadmap added. Next: implementation.*

*Reviewed: JFK → HKG, Cathay Pacific (v2.3)*
*Updated: HKG → DPS, mobile chat rescue (v2.4)*
*Updated: Pre-landing HKG, semantic triggers roadmap (v2.5)*
