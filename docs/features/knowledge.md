# Knowledge System

Knowledge items store reusable insights that are automatically recalled when relevant.

## Why This Matters

### For Agents
Agents working on the same codebase can share learned patterns. When Agent B encounters authentication code, it automatically gets Agent A's insight about "JWT tokens expire after 15 minutes."

### For Learning Engineers
Knowledge items crystallize your understanding into retrievable form. Unlike notes in a document, they're **actively recalled** when you're working on related topics.

The key insight: you're not just saving facts, you're saving *your understanding* of those facts.

## Knowledge vs Checkpoints

| Aspect | Checkpoint | Knowledge |
|--------|------------|-----------|
| **Purpose** | Research state at a moment | Reusable insight |
| **Scope** | Full context (thesis, sources, tensions) | Focused fact/pattern |
| **Recall** | Explicit (load by ID or search) | Automatic (keyword triggers) |
| **Lifetime** | Point-in-time snapshot | Persists until outdated |

Use checkpoints for "what I learned during this research session."
Use knowledge for "facts I'll need again later."

## What to Store

### Good Knowledge Items

```markdown
# JWT Token Expiry
This codebase uses 15-minute access tokens with 7-day refresh tokens.
Refresh is single-use for security.

Keywords: jwt, token, expiry, refresh, authentication
```

```markdown
# Payment Idempotency
All payment mutations require idempotency keys. Without one,
Stripe will reject the request. Keys are UUIDs in the X-Idempotency-Key header.

Keywords: payment, stripe, idempotency, mutation
```

```markdown
# Database Migration Pattern
Migrations are in src/db/migrations/ using Alembic.
Run with: alembic upgrade head
Never modify committed migrations - create new ones.

Keywords: database, migration, alembic, schema
```

### What NOT to Store

- **Transient state** — "I'm currently debugging auth" → use checkpoint
- **Generic facts** — "JWT is a token format" → you can ask Claude
- **Code snippets** — "Here's the auth function" → use code refs

Store insights that are:
1. **Specific** to this codebase/project
2. **Reusable** across sessions
3. **Non-obvious** (you'd forget or have to rediscover)

## Knowledge Types

| Type | Purpose | Recall Threshold |
|------|---------|------------------|
| `knowledge` | General facts (default) | 0.70 |
| `preference` | User preferences ("I prefer...") | 0.30 (aggressive) |
| `todo` | Persistent reminders | 0.40 |
| `reference` | On-demand reference material | 0.80 (conservative) |

### Preferences

Lower threshold for things that should influence most work:

```python
sage_save_knowledge(
    knowledge_id="prefer-fp",
    content="I prefer functional programming patterns. Avoid mutation, use pure functions.",
    keywords=["style", "code", "pattern"],
    item_type="preference"
)
```

### Todos

Persistent reminders that surface when relevant:

```python
sage_save_knowledge(
    knowledge_id="todo-auth-cleanup",
    content="TODO: Refactor auth middleware to use dependency injection",
    keywords=["auth", "middleware", "refactor"],
    item_type="todo"
)
```

**Source:** [`sage/knowledge.py`](../../sage/knowledge.py)

## Usage

### Saving Knowledge

```python
# Via MCP
sage_save_knowledge(
    knowledge_id="jwt-expiry",           # Unique ID (kebab-case)
    content="Access tokens expire after 15 minutes...",
    keywords=["jwt", "token", "expiry"],  # Trigger words
    skill="auth-system",                  # Optional: scope to skill
    source="Found in config.py:42",       # Where you learned this
    item_type="knowledge"                 # knowledge|preference|todo|reference
)
```

```bash
# Via CLI
sage knowledge add notes.md --id jwt-expiry --keywords jwt,token,expiry
```

### Automatic Recall

Knowledge is injected when queries match keywords:

```
User: "What do we know about JWT tokens?"
Claude: [calls sage tool]
        [gets auto-injected: jwt-expiry knowledge]
        "Based on what I know about this project..."
```

### Manual Recall

```python
# Explicit recall
sage_recall_knowledge(
    query="authentication token handling",
    skill="auth-system"  # Optional: scope filter
)
```

### Listing and Managing

```python
sage_list_knowledge(skill="auth-system")
sage_update_knowledge(knowledge_id="jwt-expiry", content="Updated...")
sage_deprecate_knowledge(knowledge_id="old-insight", reason="Outdated since v2")
sage_archive_knowledge(knowledge_id="obsolete-item")
sage_remove_knowledge(knowledge_id="wrong-item")
```

```bash
sage knowledge list
sage knowledge match "authentication"  # Test what would be recalled
sage knowledge rm jwt-expiry
```

## Hybrid Scoring

Knowledge recall uses both semantic similarity and keyword matching:

```
Score = 0.70 × semantic_similarity + 0.30 × keyword_match
```

This means:
- Semantically similar content matches even without exact keywords
- Exact keyword matches boost relevance
- Both methods complement each other

Configurable via `embedding_weight` and `keyword_weight` in tuning.yaml.

**Source:** [`sage/knowledge.py:280-350`](../../sage/knowledge.py)

## Knowledge Scoping

Knowledge can be scoped to specific skills:

```python
sage_save_knowledge(
    knowledge_id="stripe-webhooks",
    content="Webhooks need signature verification...",
    keywords=["stripe", "webhook"],
    skill="payments"  # Only recalls when payments skill is active
)
```

Scoped knowledge only surfaces when working in that context.

## Lifecycle Management

### Deprecation

Mark knowledge as outdated without deleting:

```python
sage_deprecate_knowledge(
    knowledge_id="old-auth-pattern",
    reason="Replaced by JWT in v2.0",
    replacement_id="jwt-expiry"  # Optional: point to replacement
)
```

Deprecated items still appear in search but show a warning.

### Archiving

Hide from recall but preserve:

```python
sage_archive_knowledge(knowledge_id="obsolete-item")
```

To restore: `sage_update_knowledge(knowledge_id, status="active")`

### Staleness Detection

Knowledge can become stale when code changes. Future feature: detect when `code_refs` in knowledge items point to changed code.

See [Knowledge Decay](../design-knowledge-decay.md) for design discussion.

## Learning-Oriented Usage

### The Learning Pattern

After understanding something through research:

```python
# 1. Checkpoint captures the full research context
sage_save_checkpoint(
    core_question="How does the payment idempotency work?",
    thesis="All mutations require idempotency keys...",
    confidence=0.9,
    reasoning_trace="Traced the flow from API to Stripe..."
)

# 2. Knowledge extracts the reusable insight
sage_save_knowledge(
    knowledge_id="payment-idempotency",
    content="All payment mutations require idempotency keys...",
    keywords=["payment", "stripe", "idempotency"],
    source="Research checkpoint 2026-02-13T12-00-00"
)
```

The checkpoint preserves *how you learned*. The knowledge preserves *what to remember*.

### The Anti-Pattern

```
AI: "Here's how idempotency works..."
You: "Save that as knowledge"
```

You've saved the AI's explanation, not your understanding. When you recall it later, you'll get information without the context of *why* it matters or *how* you verified it.

Better:

```
You: [researches idempotency in the actual code]
You: [understands why keys are required]
You: "Save knowledge: I learned that idempotency keys are required because..."
```

Now the knowledge item reflects your understanding, not just received information.

## Storage

### Format

Markdown with YAML frontmatter:

```markdown
---
id: jwt-expiry
type: knowledge
keywords:
  - jwt
  - token
  - expiry
source: Found in config.py:42
added: '2026-02-13'
skill: auth-system
---

Access tokens in this codebase expire after 15 minutes.
Refresh tokens are valid for 7 days but single-use.
```

### Location

```
~/.sage/knowledge/
├── index.yaml           # Knowledge index
└── content/
    ├── jwt-expiry.md
    └── payment-idempotency.md

<project>/.sage/knowledge/
├── index.yaml           # Project-specific knowledge
└── content/
    └── ...
```

## Configuration

```yaml
# ~/.sage/tuning.yaml

# Recall thresholds
recall_threshold: 0.70        # Base threshold for recall
dedup_threshold: 0.90         # Similarity for deduplication

# Scoring weights
embedding_weight: 0.70        # Semantic similarity weight
keyword_weight: 0.30          # Keyword match weight

# Caching
knowledge_cache_ttl_seconds: 45.0  # Index cache TTL

# Maintenance
knowledge_max_age_days: 0     # Prune old knowledge (0 = never)
```

## Related

- [Checkpointing](./checkpointing.md) — Full research state snapshots
- [Embeddings](./embeddings.md) — Semantic similarity for recall
- [Storage Maintenance](./maintenance.md) — Pruning and caching
