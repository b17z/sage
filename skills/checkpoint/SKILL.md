---
name: checkpoint
description: Semantic checkpointing for research and complex tasks
auto_invoke: true
triggers:
  - synthesis moment detected
  - branch point identified
  - hypothesis validated or invalidated
  - topic transition
  - user says "checkpoint", "save this", "remember this"
---

# Checkpoint Skill

You have the ability to create semantic checkpoints that preserve research state across context windows. Use this proactively when you detect state transitions.

## When to Checkpoint

Checkpoint when you detect:

| Signal | Example Phrases |
|--------|-----------------|
| Conclusion reached | "So the answer is...", "This means...", "Therefore..." |
| Hypothesis validated | "This confirms...", "This rules out..." |
| Branch point | "We could either X or Y", "Two approaches..." |
| Constraint discovered | "Wait, that changes things...", "I didn't realize..." |
| Topic transition | Shift in focus, new entity/concept |
| User validation | "That makes sense", "Let's go with that", "Agreed" |
| Explicit request | "checkpoint", "save this", "remember this" |

## Checkpoint Format

When checkpointing, create a structured block:

```checkpoint
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

## Storage

Save checkpoints to `.sage/checkpoints/` in the current project, or `~/.sage/checkpoints/` for global research.

Filename format: `YYYY-MM-DDTHH-MM-SS_short-description.yaml`

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

## Behavior

- **Proactive**: Don't wait to be asked. When you detect a checkpoint-worthy moment, save it.
- **Lightweight**: Brief notification to user ("Checkpointed: [description]"), don't disrupt flow.
- **Cumulative**: Each checkpoint builds on previous, creating a research trail.
