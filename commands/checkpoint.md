---
description: Create a semantic checkpoint of current research state
---

# /checkpoint

Extract and save a semantic checkpoint from the current conversation.

## Instructions

Create a checkpoint capturing the current research/work state using this schema:

```yaml
checkpoint:
  id: [YYYY-MM-DDTHH-MM-SS]_[short-description]
  trigger: manual

  core_question: |
    What decision or action is this work driving toward?

  thesis: |
    Current synthesized position or understanding (1-2 sentences)
  confidence: [0.0-1.0]

  open_questions:
    - What's still unknown or needs investigation?

  sources:
    - id: [identifier]
      type: [person | document | code | observation]
      take: [Decision-relevant summary, 1-2 sentences]
      relation: [supports | contradicts | nuances]

  tensions:
    - between: [source1, source2]
      nature: What they disagree on
      resolution: [unresolved | resolved]

  unique_contributions:
    - type: [discovery | experiment | synthesis]
      content: What was discovered that wasn't obvious

  action:
    goal: What's being done with this work
    type: [decision | implementation | learning | exploration]
```

## Output

1. Generate the checkpoint YAML based on the conversation
2. Save to `.sage/checkpoints/[id].yaml` in the current project
3. Briefly confirm what was captured

## Compression Principles

- **Compress for decisions, not completeness** - ask "would this change the decision?"
- **Preserve tensions** - disagreements between sources are high-value
- **Elevate unique contributions** - discoveries that aren't in external sources
- **Drop re-derivable content** - keep conclusions, not full reasoning chains
