---
name: sage-knowledge-hygiene
description: Evaluate and maintain knowledge freshness - detect and fix stale knowledge
triggers: [stale knowledge, outdated, knowledge recalled, update knowledge, deprecated, freshness, knowledge hygiene]
author: sage
version: 1.0.0
---

# Knowledge Hygiene

When knowledge is recalled, evaluate its freshness. Stale knowledge injects wrong context.

## Staleness Signals

| Signal | How to Detect | Example |
|--------|---------------|---------|
| **Version mismatch** | Knowledge mentions old version | "Post v2.4" when we're on v2.6 |
| **Temporal markers** | "TODO", "planned", "upcoming", "will be" | Feature listed as TODO but shipped |
| **Contradiction** | Recalled content conflicts with current facts | "Not implemented" but we just used it |
| **Date references** | Specific dates in the past | "Q1 2025 roadmap" |

## Type-Specific Evaluation

Different knowledge types decay differently:

| Type | Decay Rate | Evaluate For |
|------|------------|--------------|
| `knowledge` | Medium | Version refs, temporal markers, contradictions |
| `preference` | Very slow | Only explicit user contradiction |
| `todo` | Fast | Completion, age without action (30+ days) |
| `reference` | Slow | Source validity, version refs |

## When to Evaluate

1. **On recall** - Quick scan when knowledge is surfaced
2. **Session start** - Review proactively recalled items
3. **After version bump** - Check for version-specific knowledge
4. **Explicit request** - User asks to review knowledge

## Remediation Actions

### If content is wrong/outdated:
```python
sage_update_knowledge(
    knowledge_id="the-id",
    content="Updated accurate content",
)
```

### If superseded but worth keeping for history:
```python
sage_deprecate_knowledge(
    knowledge_id="the-id",
    reason="Superseded by v2.6 skills architecture",
    replacement_id="new-knowledge-id",  # optional
)
```

### If no longer relevant:
```python
sage_archive_knowledge(knowledge_id="the-id")
```

### If still valid (bump freshness):
```python
sage_update_knowledge(
    knowledge_id="the-id",
    content=None,  # Keep content
    # Just accessing it updates last_recalled internally
)
```

## Quick Hygiene Check

When you see recalled knowledge, ask:

1. **Version check**: Does it reference an old version?
2. **Completion check**: Does it list something as TODO that's done?
3. **Contradiction check**: Does it conflict with what we know now?

If any answer is yes -> remediate immediately.

## Example: Stale Feature List

Recalled knowledge says:
> "Post v2.4.0 - TODO: Proactive recall on session start"

But we're on v2.6 and proactive recall shipped in v2.5.

**Action:**
```python
sage_update_knowledge(
    knowledge_id="feature-ideas",
    content="Updated content marking proactive recall as shipped...",
)
```
