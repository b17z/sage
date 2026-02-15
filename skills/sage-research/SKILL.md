---
name: sage-research
description: Research methodology - when and how to checkpoint with Sage
triggers: [research, synthesis, hypothesis, conclude, investigation, summarize, therefore, branch point, checkpoint, save this, remember this, save my research]
author: sage
version: 1.1.0
---

# Sage Research Methodology

Checkpoint at **state transitions**, not token pressure.

## When to Checkpoint

| Trigger | Signal | Confidence |
|---------|--------|------------|
| `synthesis` | "Therefore...", "In summary...", "The answer is..." | 0.5+ |
| `web_search_complete` | After processing search results | 0.3+ |
| `branch_point` | "We could either X or Y..." | 0.4+ |
| `constraint_discovered` | "This won't work because..." | 0.4+ |
| `topic_shift` | Conversation changing direction | 0.4+ |
| `manual` | User says "checkpoint" or "save this" | 0.0 (always) |

### Signal Detection

| Signal | Example Phrases |
|--------|-----------------|
| Conclusion reached | "So the answer is...", "This means...", "Therefore..." |
| Hypothesis validated | "This confirms...", "This rules out..." |
| Branch point | "We could either X or Y", "Two approaches..." |
| Constraint discovered | "Wait, that changes things...", "I didn't realize..." |
| Topic transition | Shift in focus, new entity/concept |
| User validation | "That makes sense", "Let's go with that", "Agreed" |
| Explicit request | "checkpoint", "save this", "remember this" |

## The Research Workflow

```
WebSearch -> synthesize findings -> sage_autosave_check -> respond to user
```

**A research task is NOT complete until `sage_autosave_check` is called.**

## What to Capture

```python
sage_autosave_check(
    trigger_event="synthesis",           # What triggered this
    core_question="What are we solving?", # The driving question
    current_thesis="Our current position", # 1-2 sentence synthesis
    confidence=0.7,                       # How confident (0-1)
    open_questions=["What's still unknown?"],
    key_evidence=["Concrete facts supporting thesis"],
)
```

## Responding to Hook Detections

When you see these messages from hooks, act immediately:

- **Synthesis detected** -> `sage_autosave_check(trigger_event='synthesis', ...)`
- **Branch point detected** -> `sage_autosave_check(trigger_event='branch_point', ...)`
- **Constraint discovered** -> `sage_autosave_check(trigger_event='constraint_discovered', ...)`
- **Topic shift detected** -> `sage_autosave_check(trigger_event='topic_shift', ...)`

**Never ignore hook detection messages.** They indicate checkpoint-worthy moments.

## Before Changing Topics

Always checkpoint before moving to a new subject:

```python
sage_autosave_check(
    trigger_event="topic_shift",
    core_question="Previous topic question",
    current_thesis="Where we landed",
    confidence=0.6,
)
```

## Autosave Triggers (Game Analogy)

Think of checkpointing like a game's autosave system:

| Trigger Event | When | Game Analogy |
|---------------|------|--------------|
| `research_start` | User asks research question | Entering boss room |
| `web_search_complete` | After processing web search results | Picked up item |
| `synthesis` | You say "So...", "Therefore...", "In summary..." | Quest complete |
| `topic_shift` | User pivots to new topic | Switching levels |
| `user_validated` | User confirms your finding | Checkpoint reached |
| `constraint_discovered` | New info changes approach | Plot twist |
| `branch_point` | Multiple viable paths identified | Fork in road |

## Checkpoint Schema

When checkpointing, this data is captured:

```yaml
id: [timestamp]_[short-description]
trigger: [manual | synthesis | branch_point | constraint | transition]

core_question: |
  What decision or action is this research driving toward?

thesis: |
  Current synthesized position (1-2 sentences)
confidence: [0.0-1.0]

open_questions:
  - What's still unknown?
  - What needs more research?

sources:
  - id: [identifier]
    type: [person | document | api | observation]
    take: [Decision-relevant summary, 1-2 sentences]
    relation: [supports | contradicts | nuances]

tensions:
  - between: [source1, source2]
    nature: What they disagree on
    resolution: [unresolved | resolved | moot]

unique_contributions:
  - type: [discovery | experiment | synthesis | internal_knowledge]
    content: What WE found that isn't in external sources

action:
  goal: What's being done with this research
  type: [decision | output | learning | exploration]
```

## Compression Principles

1. **Compress for decisions, not completeness** - "Would this change the decision?"
2. **Preserve tensions** - Disagreements between credible sources are high-value
3. **Elevate unique contributions** - Your discoveries are differentiated value
4. **Drop re-derivable content** - Keep conclusions, not the reasoning chain

## Restoration

When continuing from a checkpoint, inject it as context:

```markdown
# Research Context (Restored from Checkpoint)

## Core Question
[core_question]

## Current Thesis (confidence: X%)
[thesis]

## Open Questions
[open_questions as bullets]

## Key Sources
[sources with relation indicators: [+] supports, [-] contradicts, [~] nuances]

## Tensions
[unresolved disagreements]

## Unique Discoveries
[unique_contributions]
```

## Saving Reusable Knowledge

When you learn something worth remembering across sessions:

```python
sage_save_knowledge(
    knowledge_id="kebab-case-id",
    content="The insight in markdown",
    keywords=["trigger", "words", "for", "recall"],
)
```

## Recalling Knowledge

Before starting work, check what's already known:

```python
sage_recall_knowledge(query="what you're working on")
```

## Presenting Checkpoints

When loading or listing checkpoints, format them nicely for the user:

### Single Checkpoint
```markdown
## 📍 Authentication Flow Analysis
*Saved 2026-02-14 | Confidence: 85%*

**Question:** How does the authentication flow work in this codebase?

**Thesis:** Authentication uses JWT tokens with refresh rotation. The flow
starts in auth/login.py, validates credentials against the user service,
and issues tokens via auth/tokens.py.

**Key Evidence:**
- Access tokens expire in 15 minutes
- Refresh tokens stored in httponly cookies

**Open Questions:**
- How does token revocation work?
- Is there rate limiting on login attempts?

**Sources:**
- [+] auth/login.py — Entry point for login
- [+] auth/tokens.py — JWT generation
- [+] RFC 7519 — JWT standard followed
```

### Checkpoint List
```markdown
Found **3 checkpoints**:

| Checkpoint | Confidence | When |
|------------|------------|------|
| authentication-flow | 85% | Feb 14 |
| rate-limiting-design | 70% | Feb 13 |
| api-structure | 90% | Feb 12 |

Use `sage_load_checkpoint("authentication-flow")` to restore context.
```

### Relation Icons
- `[+]` supports — Source confirms the thesis
- `[-]` contradicts — Source challenges the thesis
- `[~]` nuances — Source adds complexity/conditions

## Behavior

- **Proactive**: Call autosave checks at trigger moments. Don't wait to be asked.
- **Lightweight**: Brief notification, don't disrupt flow.
- **Cumulative**: Each checkpoint builds on previous, creating a research trail.
