# Checkpoint Methodology for Sage

*A framework for semantic checkpointing in AI-assisted research*

---

## The Problem

Context windows are finite. Research is iterative. The current solutions—autocompaction, summarization, RAG—are all **reactive and lossy**. They compress under pressure without understanding what matters.

The result: you become the orchestration layer, manually maintaining state across 20+ fragmented chat sessions like a Beautiful Mind conspiracy board.

---

## The Core Principle

> **Compress to the point where you could reconstruct the conversation's strategic direction, not the conversation itself.**

You don't need to remember every tweet analyzed or every tangent explored. You need to remember:
- What decision you're driving toward
- What you've concluded (and why)
- Where credible sources disagree
- What you uniquely discovered

Everything else is retrievable or re-derivable.

---

## Semantic Checkpointing vs. Autocompaction

| Dimension | Autocompaction | Semantic Checkpointing |
|-----------|----------------|------------------------|
| **Trigger** | Token pressure (reactive) | State transition (proactive) |
| **Mechanism** | Lossy compression | Selective persistence |
| **What's saved** | Summarized conversation | Validated conclusions + open questions |
| **Mental model** | "Shrink everything" | "Graduate stable knowledge" |
| **Resume experience** | Re-derive from compressed context | Continue from known state |
| **Branching** | Brutal—branch overwrites context | Restore checkpoint, explore branch |

The key insight: checkpointing isn't about saving tokens. It's about **committing validated state** so you can discard the derivation path.

---

## When to Checkpoint: State Transitions

Research has detectable state transitions, analogous to game autosave triggers:

| Game Autosave | Research Equivalent | Detection Signal |
|---------------|---------------------|------------------|
| Boss defeated | Hypothesis validated/invalidated | "So the answer is...", "This confirms...", "This rules out..." |
| Entered new room | Topic/subquestion transition | Shift in search queries, new entity focus |
| Acquired key item | Critical constraint discovered | "Wait, that changes things...", "I didn't realize..." |
| Before major choice | Branch point | "We could either X or Y", "Option A vs Option B" |
| Cutscene started | Synthesis moment | "Putting this together...", "The thesis is..." |
| User saved manually | Explicit checkpoint request | User says "checkpoint", "save this", "remember this" |

### Detection Heuristics

The LLM can recognize its own state transitions. High-confidence signals:

**Conclusion Language**
- "So the best option is..."
- "This means..."
- "Therefore..."
- "The answer is..."
- "We can conclude..."

**User Validation**
- "That makes sense"
- "Let's go with that"
- "Good point"
- "That works"
- "Agreed"

**Constraint Discovery**
- "Oh, this changes things because..."
- "I didn't realize X meant Y"
- "Wait, that means..."
- "New constraint:..."

**Branch Presentation**
- "Option A vs Option B"
- "We could either..."
- "Two approaches:..."
- "Fork in the road:..."

**Search Consolidation**
- After N searches on related subtopics
- When synthesizing across multiple sources
- Transition from gathering to concluding

---

## The Checkpoint Schema

A checkpoint captures enough to reconstruct direction, not conversation.

### Universal Core

```yaml
checkpoint:
  # Identity
  id: string                    # UUID
  created_at: timestamp
  trigger: string               # manual | token_threshold | synthesis | handoff | branch_point
  
  # Lineage
  parent_id: string | null      # For chains
  branch_from: string | null    # For branches
  
  # The Most Important Field
  core_question: string         # What decision/action is this research driving toward?
  
  # Current Synthesis
  thesis: string                # The synthesized position/framework
  confidence: float             # 0-1, how confident in synthesis
  open_questions:               # What's still unknown
    - string
  
  # Sources (compressed)
  sources:
    - id: string
      type: string              # person | document | api | experiment | observation
      identifier: string        # Name, URL, handle—whatever identifies it
      credibility: string       # Why trust this? (role, publication, track record)
      core_take: string         # 1-2 sentences—the DECISION-RELEVANT summary
      relation: string          # supports | contradicts | nuances | context
  
  # Tensions (high value—always preserve)
  tensions:
    - sources: [id, id]         # Which sources disagree
      nature: string            # What they disagree on
      resolution: string        # unresolved | resolved | moot
  
  # User's Unique Contributions (elevated priority)
  unique_contributions:
    - type: string              # discovery | experiment | synthesis | internal_knowledge
      content: string
  
  # Action Context
  action:
    goal: string                # What's being done with this info
    goal_type: string           # decision | output | learning | exploration
    deadline: timestamp | null
    stakeholders: [string]
  
  # Domain Extension
  domain: string                # general | competitive_intel | technical | literature | etc.
  domain_data: object           # Domain-specific fields (see extensions)
  
  # Metadata
  token_estimate: int           # Approximate tokens when serialized
  compression_ratio: float      # original_context_tokens / checkpoint_tokens
```

### Why This Schema

| Field | Why It Exists |
|-------|---------------|
| `core_question` | Everything organizes around the decision being made. Without this, you're just collecting facts. |
| `thesis` | The synthesized position. This is what you'd tell someone in 30 seconds. |
| `confidence` | Epistemic honesty. A 0.3 confidence thesis means "working hypothesis, not conclusion." |
| `open_questions` | What you'd research next. Prevents re-exploring closed questions. |
| `sources` | Compressed to decision-relevance. Not "what did they say" but "how does it affect the thesis." |
| `tensions` | Disagreements between credible sources are where insight lives. Always preserve. |
| `unique_contributions` | What YOU bring—not in the external discourse. Your differentiated insight. |
| `action` | Checkpoints are for decisions, not just knowledge storage. What are you doing with this? |
| `domain_data` | Flexibility for domain-specific needs without polluting the core schema. |

---

## Source Compression

For each source, extract only what's decision-relevant:

| Before | After |
|--------|-------|
| 800+ words across multiple tweets about payment network history, forcing functions, PayPal, WeChat, Starbucks, AI agents... | "POS checkout is dead end. No forcing function. Every successful network had exclusivity or killer reward. Exception: maybe AI agents." |
| Full API documentation for competitor's SDK | "Supports 3 payment types, no escrow, merchant-side only. Gap: no consumer wallet integration." |
| 45-minute meeting transcript | "Decision: go with Option B. Blocker: legal review. Owner: Sarah. Timeline: 2 weeks." |

### The Compression Test

Ask: **"If I only had this summary, could I make the same decision I would with the full source?"**

- If yes → compression is sufficient
- If no → you're losing decision-relevant signal

---

## Preserving Tensions

Disagreements between credible sources are high-value. Don't resolve them prematurely—capture them:

```yaml
tensions:
  - sources: ["sheel_mohnot", "sam_broner"]
    nature: "Forcing function for stablecoin POS adoption"
    resolution: unresolved
    # Sheel: "No forcing function exists"
    # Sam: "Merchant profitability IS the forcing function"
    
  - sources: ["internal_api_docs", "competitor_announcement"]  
    nature: "Who has escrow support"
    resolution: resolved
    # Initially thought competitor had it, confirmed they don't
```

Tensions often reveal:
- Where the conventional wisdom might be wrong
- Where your unique insight could add value
- What needs more research before deciding

---

## Unique Contributions

What do YOU bring that external sources don't? This gets elevated because it's differentiated:

- **Discoveries**: "Platform lead didn't know about existing SDK integration"
- **Experiments**: "Built prototype with 7 payment types, confirmed fragmentation"
- **Internal knowledge**: "Our API actually does support this, it's just undocumented"
- **Synthesis**: "The pattern across all these sources is X" (when you're the one who saw the pattern)

These are the insights that make your research valuable beyond just aggregating public information.

---

## Domain Extensions

The core schema handles universal research needs. Domain extensions add specialized fields.

### Competitive Intelligence

```yaml
domain: competitive_intel
domain_data:
  competitive_moves:
    - company: string
      action: string
      timeline: string
      threat_level: high | medium | low
  internal_state:
    products: [string]
    gaps: [string]
    fragmentation_notes: string
  key_people:
    - name: string
      role: string
      relevance: string  # Why they matter to the decision
```

**High-value signals for this domain:**
- Competitor timelines and announcements
- Internal gaps and fragmentation
- Acquisition/partnership moves
- Who's talking to whom

### Technical Investigation

```yaml
domain: technical
domain_data:
  problem:
    symptoms: [string]
    reproduction: string
    constraints: [string]
  hypotheses:
    - hypothesis: string
      status: untested | confirmed | rejected
      evidence: string
  ruled_out: [string]  # Valuable to know what doesn't work
  solution_space:
    - approach: string
      tradeoffs: string
      viability: high | medium | low
```

**High-value signals for this domain:**
- Root cause identification
- Reproduction steps
- Failed hypotheses (knowing what doesn't work is valuable)
- Constraint discoveries

### Literature Review

```yaml
domain: literature
domain_data:
  theoretical_frameworks:
    - name: string
      sources: [id]
      core_claims: [string]
  methodology_notes:
    - source_id: string
      methodology: string
      limitations: string
      sample_size: string | null
  evidence_quality:
    - source_id: string
      quality: high | medium | low
      reasoning: string
  replication_status:
    - finding: string
      replicated: yes | no | mixed
      notes: string
```

**High-value signals for this domain:**
- Meta-analyses and systematic reviews
- Replication status of key findings
- Methodological contradictions
- Gaps in the literature

### General Research (Default)

When no specific domain applies, `domain_data` stays empty and the core schema handles everything. The core schema is designed to be sufficient for 80% of research tasks.

---

## Checkpoint Lifecycle

### Creation Triggers

| Trigger | When | Who Initiates |
|---------|------|---------------|
| `manual` | User explicitly requests | User |
| `token_threshold` | Approaching context limit (e.g., 80% full) | System |
| `synthesis` | Major conclusion reached | LLM detects, user confirms |
| `handoff` | Passing to another agent | System |
| `branch_point` | About to explore divergent path | LLM suggests |
| `session_end` | Ending research session | System |

### The Three-Tier Model

**Tier 1: Manual but Frictionless**

User says "checkpoint" → LLM extracts structured checkpoint automatically. No thinking about what to capture.

```
User: checkpoint
Assistant: <checkpoint>
  core_question: "Best flight routing JFK → Philippines → Singapore → back"
  thesis: "SIN → CRK is the key insight—direct flight exists, Clark is 1.5hr from Olongapo vs 3-4hr from Manila"
  confidence: 0.8
  ...
</checkpoint>
Checkpointed. Continue?
```

**Tier 2: LLM Suggests, User Confirms**

LLM detects state transition, asks for confirmation:

```
Assistant: I think we just locked in that Clark is the exit point. Want me to checkpoint this?
User: y
Assistant: <checkpoint>...</checkpoint>
Done. The key insight saved: SIN→CRK direct + Clark proximity.
```

**Tier 3: Fully Automatic**

LLM checkpoints silently at detected transitions. User can review/edit later. Best for high-frequency research where interruptions break flow.

### Restoration

When resuming, inject the checkpoint as context:

```markdown
# Research Context (Restored from Checkpoint)

## Core Question
Best flight routing JFK → Philippines → Singapore → back

## Current Thesis (confidence: 80%)
SIN → CRK is the key insight—direct flight exists, Clark is 1.5hr from Olongapo vs 3-4hr from Manila

## Open Questions
- Wheelchair assistance availability on Scoot SIN→CRK
- Return routing through Taiwan vs direct

## Key Sources
[+] Google Flights: SIN→CRK direct exists on Scoot, ~$80
[-] Initial assumption: Manila is the obvious Philippines hub
[~] Uncle's constraint: needs wheelchair assistance, Green Card re-entry at LAX

## Unique Discoveries
- Clark airport is dramatically closer to Olongapo than Manila (1.5hr vs 3-4hr)
- Direct SIN→CRK exists despite Clark being "secondary" airport

## Goal
Book flights for January trip with uncle
```

The LLM continues from this state without needing the full conversation history.

### Branching

Before exploring a divergent path:

```
Current checkpoint: cp_abc123 (thesis: "Go with Stripe integration")

User: Actually, let's explore what the Square option would look like
Assistant: Branching from current checkpoint. I'll save this branch point so we can return if needed.

<checkpoint branch_from="cp_abc123">
  id: cp_def456
  core_question: [same]
  thesis: "Exploring Square as alternative to Stripe"
  ...
</checkpoint>
```

To return: `restore cp_abc123`

### Merging

When parallel research threads need to combine:

```yaml
checkpoint:
  id: cp_merged_789
  merge_sources: [cp_agent_a, cp_agent_b]
  
  core_question: "Reconciled from both threads"
  
  thesis: "NEEDS SYNTHESIS"  # Flag for LLM to reconcile
  component_theses:
    - from: cp_agent_a
      thesis: "Stripe is better for US market"
    - from: cp_agent_b
      thesis: "Square has better international coverage"
  
  # Sources: union with deduplication
  # Tensions: may include cross-agent disagreements
```

The merged checkpoint flags that synthesis is needed—the LLM reconciles the component theses into a unified position.

---

## Compression Heuristics

### Always Keep (High Signal)

- Core thesis statements
- Disagreements between credible sources (tensions)
- User's unique discoveries/contributions
- Constraints that invalidate options
- Action context (goal, deadline, stakeholders)
- Open questions that need resolution

### Summarize (Medium Signal)

- Supporting evidence for thesis (keep conclusion, compress evidence)
- Background context (enough to understand, not full detail)
- Technical details (unless core to thesis)
- Source reasoning (keep the take, compress the argument)

### Drop or Reference (Low Signal)

- Tangential discussions (preserve pointer if retrievable)
- Already-resolved questions
- Duplicate information across sources
- Historical context not relevant to current decision
- Process/meta discussion ("let me search for that...")

### The Compression Test

For each piece of information, ask:

1. **Does this change the decision?** If no → drop or summarize
2. **Would I need to re-derive this?** If yes → keep
3. **Can I retrieve this if needed?** If yes → keep pointer, drop content
4. **Is this my unique contribution?** If yes → keep (differentiated value)

---

## Implementation Notes

### For Sage Integration

The checkpoint system integrates with Sage's existing architecture:

```
~/.sage/
├── checkpoints/
│   ├── {checkpoint_id}.yaml    # Checkpoint data
│   └── index.yaml              # Checkpoint index with metadata
├── skills/
│   └── {skill}/
│       └── checkpoints/        # Per-skill checkpoint references
└── config.yaml                 # Checkpoint settings
```

### Checkpoint as Context Injection

When restoring, the checkpoint serializes to markdown (`.to_context_prompt()`) for injection into the conversation. This is the "rehydration" step.

### Extraction Prompt

The LLM needs instructions for extracting checkpoints. Key elements:

```markdown
You are creating a research checkpoint. Extract the following from our conversation:

1. CORE QUESTION: What decision/action is this research driving toward?
2. THESIS: What's your current synthesized position? (1-2 sentences)
3. CONFIDENCE: 0-1, how confident in the thesis?
4. OPEN QUESTIONS: What's still unknown? (max 5)
5. SOURCES: For each significant source:
   - Who/what is it?
   - What's the decision-relevant take? (1-2 sentences)
   - Does it support, contradict, or nuance the thesis?
6. TENSIONS: Where do credible sources disagree?
7. UNIQUE CONTRIBUTIONS: What did WE discover that isn't in external sources?
8. ACTION: What's being done with this research? Any deadline?

Output as YAML in <checkpoint> tags.

IMPORTANT: Compress for decision-relevance, not completeness. Someone should be able to continue this research from your checkpoint without the full conversation.
```

### Token Estimation

Track approximate tokens to know compression ratio:

```python
def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token for English."""
    return len(text) // 4
```

More accurate: use `tiktoken` or Anthropic's tokenizer.

---

## Examples

### Before: Raw Conversation State

```
- 15 tweets analyzed across 8 accounts
- 4 articles fetched and discussed  
- 3 API docs reviewed
- 2 hours of back-and-forth
- Multiple tangents (PayPal history, WeChat, UPI, AI agents)
- ~45,000 tokens of context
```

### After: Checkpoint

```yaml
checkpoint:
  id: cp_20260109_crypto_payments
  trigger: synthesis
  
  core_question: "Where do stablecoins actually win vs. traditional payment rails, and what's the product opportunity?"
  
  thesis: "Integrate, don't replace. Stablecoins win middle mile + new primitives, not POS. Most companies have pieces but not packaging."
  confidence: 0.75
  
  open_questions:
    - "What's the unified customer object strategy?"
    - "Who owns the packaging problem internally?"
    - "Timeline for Stripe's full stack vs current fragmentation?"
  
  sources:
    - id: sheel
      type: person
      identifier: "@sheel (Sheel Mohnot)"
      credibility: "Fintech investor, Payment network history expertise"
      core_take: "No forcing function for stablecoin POS. Every successful payment network had exclusivity or killer reward."
      relation: contradicts  # to "stablecoins will replace cards at POS"
      
    - id: simon
      type: person  
      identifier: "@sytaylor (Simon Taylor)"
      credibility: "Fintech analyst, 11:FS"
      core_take: "Not about price—about TAM expansion. Stablecoins enable payments that couldn't exist before."
      relation: nuances
      
    # ... 6 more sources, 1-2 sentences each
  
  tensions:
    - sources: [sheel, sam_broner]
      nature: "Whether merchant profitability is sufficient forcing function"
      resolution: unresolved
      
    - sources: [nikil, bruno]
      nature: "Settlement vs checkout focus"
      resolution: resolved  # Both agree settlement is the play, Bruno adds enterprise nuance
  
  unique_contributions:
    - type: discovery
      content: "Platform team didn't know about existing SDK integration possibilities"
    - type: experiment
      content: "Built prototype with 7 payment types on fragmented stack—confirmed DX issues firsthand"
    - type: internal_knowledge
      content: "Teams weren't aware of certain integration possibilities across the org"
  
  action:
    goal: "Prepare for meeting with Head of Payments, find where to plug in"
    goal_type: decision
    deadline: 2026-01-09T18:00:00Z
    stakeholders: [Head of Payments, Payments org]
  
  domain: competitive_intel
  domain_data:
    competitive_moves:
      - company: Stripe
        action: "Bridge + Privy + Tempo + Klarna acquisitions"
        timeline: "12-18 month integration window"
        threat_level: high
    internal_gaps:
      - "No unified Customer Object"
      - "Fragmented payment types across teams"
      - "DX issues for developers"
  
  token_estimate: 850
  compression_ratio: 0.019  # 850 / 45000
```

**Compression: 45,000 tokens → 850 tokens (98% reduction) while preserving decision-making capability.**

---

## Key Takeaways

1. **Checkpoint at state transitions, not token pressure.** Proactive > reactive.

2. **Compress for decisions, not completeness.** "Would this change the decision?" is the test.

3. **Tensions are gold.** Disagreements between credible sources are where insight lives.

4. **Elevate unique contributions.** What YOU discovered is your differentiated value.

5. **Core question anchors everything.** Without knowing the decision, you can't prioritize.

6. **Restoration should feel like continuation.** A fresh LLM with the checkpoint should be able to pick up seamlessly.

---

*Version: 1.0.0*
*Last updated: 2026-01-09*
