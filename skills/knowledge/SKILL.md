---
name: knowledge
description: Automatic knowledge recall from stored insights
auto_invoke: true
triggers:
  - query matches stored knowledge keywords
  - user asks about previously researched topic
  - continuation of prior research thread
  - user says "recall", "what do we know about", "remember"
---

# Knowledge Recall Skill

You have access to a knowledge base of stored insights, decisions, and research findings. When a query relates to stored knowledge, relevant items are automatically injected into your context.

## How It Works

Knowledge items are stored in `~/.sage/knowledge/` with keyword triggers. When your query matches those triggers, the relevant knowledge is automatically recalled and injected.

You'll see a notification like:
```
📚 Knowledge recalled (2)
   ├─ gdpr-summary (~450 tokens)
   └─ consent-patterns (~280 tokens)
```

## What Gets Stored as Knowledge

Knowledge items capture durable insights that are useful across sessions:

| Type | Example |
|------|---------|
| Research conclusions | "GDPR Article 6 requires explicit consent for AI training" |
| Validated decisions | "We chose PostgreSQL over MongoDB because..." |
| Domain expertise | API patterns, regulatory summaries, technical constraints |
| User preferences | "Prefers academic sources", "Wants concise answers" |
| Project context | Tech stack, architecture decisions, constraints |

## Storage Structure

```
~/.sage/knowledge/
├── index.yaml              # Registry with triggers
├── global/                 # Available to all skills
│   └── api-patterns.md
└── skills/                 # Skill-scoped knowledge
    └── privacy/
        └── gdpr-summary.md
```

## Knowledge Item Format

Each item has:
- **id**: Unique identifier
- **keywords**: Trigger words for matching
- **scope**: Which skills can access it (empty = all)
- **content**: The actual knowledge (markdown)
- **source**: Where it came from (optional)

## Adding Knowledge

### Via CLI
```bash
sage knowledge add notes.md --id gdpr-summary --keywords "gdpr,privacy,consent"
sage knowledge add api-guide.md --id api-patterns --keywords "api,rest" --skill web-dev
```

### Via Conversation
Say "save this as knowledge" or "remember this" after discovering something worth preserving:

```
You: That's really useful about GDPR consent. Remember this.
Claude: [Extracts key insight and saves to knowledge base]
        Saved knowledge: gdpr-consent-requirements
        Keywords: gdpr, consent, legal basis
```

## Querying Knowledge

### Automatic
Just ask questions. If your query matches stored knowledge, it's injected automatically.

### Manual
```
You: What do we know about GDPR?
Claude: [Recalls and presents relevant stored knowledge]
```

### Test Matching
```bash
sage knowledge match "How does GDPR affect our API?"
```

## Behavior

- **Automatic**: Knowledge is recalled based on query keywords—no explicit request needed
- **Additive**: Multiple items can be recalled if relevant (up to token limit)
- **Scoped**: Skill-specific knowledge only appears when using that skill
- **Transparent**: Always shows what was recalled and token cost
