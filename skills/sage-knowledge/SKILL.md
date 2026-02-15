---
name: sage-knowledge
description: Recall and save insights using sage_recall_knowledge and sage_save_knowledge MCP tools
triggers: [recall, remember, what do we know, knowledge, save insight, prior knowledge, failure, didn't work, mistake]
author: sage
version: 2.0.0
---

# Knowledge Management

You have access to a knowledge base of stored insights, decisions, and research findings. When a query relates to stored knowledge, relevant items are automatically injected into your context.

## How It Works

Knowledge items are stored with keyword triggers. When your query matches those triggers, the relevant knowledge is automatically recalled and injected.

You'll see a notification like:
```
Knowledge recalled (2)
   - gdpr-summary (~450 tokens)
   - consent-patterns (~280 tokens)
```

## What Gets Stored as Knowledge

Knowledge items capture durable insights useful across sessions:

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
  index.yaml              # Registry with triggers
  {knowledge-id}.md       # Knowledge content files

<project>/.sage/knowledge/
  index.yaml              # Project-scoped registry
  {knowledge-id}.md       # Project-scoped knowledge
```

## Knowledge Item Format

Each item has:
- **id**: Unique identifier (kebab-case)
- **keywords**: Trigger words for matching
- **skill**: Optional skill scope (empty = global)
- **content**: The actual knowledge (markdown)
- **source**: Where it came from (optional)
- **item_type**: knowledge | preference | todo | reference

## Adding Knowledge

### Via MCP Tool
```python
sage_save_knowledge(
    knowledge_id="gdpr-summary",
    content="GDPR Article 6 requires...",
    keywords=["gdpr", "privacy", "consent"],
)
```

### Via CLI
```bash
sage knowledge add notes.md --id gdpr-summary --keywords "gdpr,privacy,consent"
sage knowledge add api-guide.md --id api-patterns --keywords "api,rest" --skill web-dev
```

### Via Conversation
Say "save this as knowledge" or "remember this" after discovering something worth preserving.

## Querying Knowledge

### Automatic
Just ask questions. If your query matches stored knowledge, it's injected automatically.

### Manual
```python
sage_recall_knowledge(query="what you're working on")
```

### Test Matching
```bash
sage knowledge match "How does GDPR affect our API?"
```

## Managing Knowledge

### Update existing:
```python
sage_update_knowledge(
    knowledge_id="the-id",
    content="Updated content",
)
```

### Mark as outdated:
```python
sage_deprecate_knowledge(
    knowledge_id="the-id",
    reason="Superseded by new architecture",
)
```

### Hide from recall:
```python
sage_archive_knowledge(knowledge_id="the-id")
```

### Delete permanently:
```python
sage_remove_knowledge(knowledge_id="the-id")
```

## Behavior

- **Automatic**: Knowledge is recalled based on query keywords - no explicit request needed
- **Additive**: Multiple items can be recalled if relevant (up to token limit)
- **Scoped**: Skill-specific knowledge only appears when using that skill
- **Transparent**: Always shows what was recalled and token cost

## Presenting Output

MCP tool results return structured data. **Always format Sage outputs nicely in your response** rather than relying on raw tool output.

### Knowledge Items

When presenting recalled knowledge:

```markdown
## 📚 jwt-auth-pattern
*Source: auth system analysis*

JWT authentication uses access/refresh token pairs. Access tokens are
short-lived (15min), refresh tokens longer (7 days). Store refresh tokens
in httponly cookies, access tokens in memory only.

**Code References:**
- `auth/tokens.py::create_access_token` — implements token generation
- `auth/tokens.py::create_refresh_token` — implements refresh flow
```

### Code Links

When knowledge links to code, show the chain:

```markdown
The rate limiting implementation is in `auth/middleware.py:RateLimiter`:
- Uses sliding window algorithm
- 5 attempts/minute per IP, 20/hour
- Lockout triggers email notification
```

### Multiple Items

For multiple items, use a compact summary first:

```markdown
Found **3 relevant items**: jwt-auth-pattern, rate-limiting, session-handling

### jwt-auth-pattern
[content]

### rate-limiting
[content]
```

### Staleness Indicators

Watch for staleness indicators in code links:
- `[!]` — Code has changed since knowledge was saved; may need review
- `[+]` — Code supports the knowledge
- `[~]` — Code provides context

## Failure Memory (v4.0)

Track what didn't work to avoid repeating mistakes.

### Recording Failures

```python
sage_record_failure(
    failure_id="jwt-localstorage",
    approach="Storing refresh tokens in localStorage",
    why_failed="XSS vulnerability - any JS can read localStorage",
    learned="Use httpOnly cookies for refresh tokens",
    keywords=["jwt", "refresh", "token", "localstorage"],
)
```

### Listing Failures

```python
sage_list_failures(limit=10)
```

### Presenting Failures

```markdown
## ⚠️ jwt-localstorage
**Approach:** Storing refresh tokens in localStorage
**Why failed:** XSS vulnerability - any JS can read localStorage
**Learned:** Use httpOnly cookies for refresh tokens
```

Failures are automatically recalled at session start when relevant to the current context.

## Knowledge Linking (v4.0)

Connect related knowledge items:

```python
sage_link_knowledge(
    source_id="auth-patterns",
    target_id="jwt-security",
    relation="related",  # related | supersedes | contradicts | extends
    note="Both cover authentication best practices",
    bidirectional=True,
)
```

When recalling linked knowledge, show the connections:

```markdown
## auth-patterns
[content]

**Links:**
- → jwt-security [related] — Both cover auth best practices
- → oauth-integration [extends] — OAuth builds on these patterns
```
