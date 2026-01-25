# Knowledge Decay: Design Document

**Status:** Draft
**Version:** 0.1
**Date:** 2026-01-24

## Problem Statement

Stored knowledge becomes stale. The `sage-feature-ideas-v2` example: listed "proactive recall" as TODO when it shipped in v2.5. Claude recalled it, injected outdated context, and we had to manually notice and fix.

**Goal:** Claude should recognize stale knowledge and either update it or flag it for review.

---

## Current Knowledge Types

| Type | Purpose | Current Threshold |
|------|---------|-------------------|
| `knowledge` | General facts | 0.70 |
| `preference` | User preferences | 0.30 (aggressive) |
| `todo` | Persistent reminders | 0.40 |
| `reference` | On-demand material | 0.80 (conservative) |

Each type has different staleness characteristics.

---

## Decay Signals Analysis

### Age-Based Decay

**Pros:**
- Simple to implement
- Universal signal

**Cons:**
- Poor proxy - some knowledge is timeless
- "USDC requires KYC" doesn't stale with age
- Misses immediate staleness (version bump)

**Verdict:** Weak signal, maybe tiebreaker only.

### Version Context

**Pros:**
- Direct signal for version-specific knowledge
- Easy to detect (compare `version_context` to current)
- Precise for software project knowledge

**Cons:**
- Requires tracking version when knowledge saved
- Not all knowledge is version-scoped

**Verdict:** Strong signal for project knowledge.

### Content Markers

Temporal language in the knowledge text itself:
- "planned", "TODO", "upcoming", "will be"
- "current", "now", "latest"
- Specific version references ("v2.4", "post-2.4")
- Date references ("January 2026", "Q1")

**Pros:**
- Detects staleness from content, not metadata
- Works retroactively on existing knowledge

**Cons:**
- Requires NLP/regex scanning
- False positives possible

**Verdict:** Good secondary signal.

### Contradiction Detection

When recalled knowledge conflicts with current conversation context.

**Pros:**
- Most accurate - detects actual wrongness
- Context-aware

**Cons:**
- Expensive (embedding comparison at recall time)
- Requires conversation context

**Verdict:** Ideal but complex. Maybe v2 of this feature.

### Recall Frequency

Track `last_recalled` and `recall_count`.

**Pros:**
- Signals knowledge utility
- Frequently recalled = valuable

**Cons:**
- High recall doesn't mean accurate
- Low recall might mean specialized, not stale

**Verdict:** Useful for prioritization, not staleness.

---

## Type-Specific Decay

### `knowledge` (general facts)

**Primary decay signals:**
- Version mismatch (if version_context set)
- Content markers (TODO, planned, etc.)
- Age (90-day half-life as fallback)

**Decay behavior:**
- Flag in recall output: "⚠️ May be stale (v2.4 → v2.6)"
- Trigger hygiene skill

### `preference` (user preferences)

**Primary decay signals:**
- Almost never - preferences are stable
- Only on explicit contradiction

**Decay behavior:**
- No automatic decay
- Only flag if user explicitly contradicts

### `todo` (persistent reminders)

**Primary decay signals:**
- Completion (marked done)
- Age without action (30-day threshold?)
- Repeated recall without progress

**Decay behavior:**
- Age-out warning: "⚠️ TODO pending 30+ days"
- Prompt: complete, reschedule, or delete?

### `reference` (on-demand material)

**Primary decay signals:**
- Source staleness (if URL, check if still valid?)
- Version mismatch
- Age (longer half-life, 180 days?)

**Decay behavior:**
- Conservative flagging
- "Reference may be outdated"

---

## Proposed Metadata

Add to knowledge frontmatter:

```yaml
# Existing
id: my-knowledge
type: knowledge
keywords: [...]
added: '2026-01-24'

# New for decay
version_context: "2.6.0"      # Version when written (optional)
last_recalled: '2026-01-24'   # Auto-updated on recall
recall_count: 0               # Auto-incremented
evergreen: false              # Skip decay checks if true
```

---

## Freshness Score Formula

Computed at recall time, type-specific:

```python
def compute_freshness(item: KnowledgeItem, current_version: str) -> float:
    match item.type:
        case "preference":
            return 1.0  # Preferences don't decay

        case "todo":
            days = days_since(item.added)
            return max(0.3, 1.0 - (days / 30) * 0.5)  # Gentle 30-day decay

        case "reference":
            days = days_since(item.added)
            version_penalty = 0.2 if version_mismatch(item, current_version) else 0
            return max(0.3, 1.0 - (days / 180) * 0.3) - version_penalty

        case "knowledge" | _:
            # Most aggressive decay
            version_penalty = 0.4 if version_mismatch(item, current_version) else 0
            content_penalty = 0.2 if has_temporal_markers(item.content) else 0
            days = days_since(item.added)
            age_decay = max(0, 1.0 - (days / 90) * 0.3)
            return max(0, age_decay - version_penalty - content_penalty)
```

---

## Implementation Phases

### Phase 1: Skills-Based (v2.7?)

- Create `sage-knowledge-hygiene` skill
- Triggers on: recalled knowledge, session start, explicit request
- Teaches Claude to evaluate freshness manually
- No automatic decay computation yet

### Phase 2: Metadata Tracking (v2.8?)

- Add `version_context`, `last_recalled`, `recall_count` to frontmatter
- Auto-populate on save and recall
- `evergreen` flag for opt-out

### Phase 3: Automatic Freshness (v2.9?)

- Compute freshness score at recall time
- Flag stale items in recall output
- Integrate with skill for remediation

### Phase 4: Contradiction Detection (v3?)

- Embedding comparison at recall time
- Detect when recalled knowledge conflicts with conversation
- Most accurate but most expensive

---

## Open Questions

1. **Default version_context:** Auto-populate from project version on save?
2. **Freshness threshold:** Below what score do we flag?
3. **Remediation UX:** Flag inline vs separate warning?
4. **Bulk hygiene:** Command to review all stale knowledge?
5. **Cross-type references:** Todo references knowledge that stales - cascade?

---

## Alternatives Considered

### Manual-only approach
- Rely on user to notice and update
- Current state, doesn't scale

### Aggressive auto-deprecation
- Auto-archive after threshold
- Too risky, might lose valuable knowledge

### External validation
- Ping URLs, check APIs
- Too complex, scope creep

---

## References

- Anthropic Knowledge Bases (announced, likely manual update only)
- Spaced repetition systems (Anki decay curves)
- Cache invalidation strategies (TTL, version tags)

---

## Changelog

- 2026-01-24: Initial draft
