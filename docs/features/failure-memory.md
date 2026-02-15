# Failure Memory (v4.0)

Learn from what didn't work. Sage tracks failed approaches and automatically surfaces them when you're about to make the same mistake.

## The Problem

You try an approach. It fails. Three weeks later, you've forgotten why it failed and try it again. Wasted time.

```
Week 1: "Let me store refresh tokens in localStorage"
        → Fails: XSS vulnerability

Week 4: "Let me store refresh tokens in localStorage"
        → Same failure, time wasted
```

## The Solution

Record failures when they happen. Sage recalls them automatically:

```
Week 1: sage_record_failure(
          failure_id="jwt-refresh-localstorage",
          approach="Using localStorage for refresh tokens",
          why_failed="XSS vulnerability - any JS can read localStorage",
          learned="Use httpOnly cookies for refresh tokens",
          keywords=["jwt", "refresh", "token", "localstorage"]
        )

Week 4: (researching JWT auth)
        → Sage auto-injects: "⚠️ Previously tried: localStorage for refresh tokens"
```

## Recording Failures

### MCP Tool

```python
sage_record_failure(
    failure_id="jwt-refresh-localstorage",  # Unique kebab-case ID
    approach="Using localStorage for refresh tokens",
    why_failed="XSS vulnerability - any JS on the page can read localStorage",
    learned="Use httpOnly cookies for refresh tokens instead",
    keywords=["jwt", "refresh", "token", "auth", "localstorage"],
    related_to=["auth-patterns", "jwt-security"]  # Optional: link to checkpoints/knowledge
)
```

### What Gets Stored

Failures are stored as Markdown files with YAML frontmatter:

```markdown
---
id: jwt-refresh-localstorage
type: failure
approach: "Using localStorage for refresh tokens"
keywords: [jwt, refresh, token, auth, localstorage]
related_to: [auth-patterns]
added: "2026-02-15T10:30:00"
---

## Why it failed
XSS vulnerability - any JS on the page can read localStorage.

## Learned
Use httpOnly cookies for refresh tokens instead.
```

## Listing Failures

```python
sage_list_failures(limit=10)
```

Returns formatted list:

```markdown
Failures (2):

## jwt-refresh-localstorage
*Keywords: jwt, refresh, token*
**Approach:** Using localStorage for refresh tokens
**Why failed:** XSS vulnerability - any JS on the page can read localStorage
**Learned:** Use httpOnly cookies for refresh tokens instead

## sqlite-multithread
*Keywords: sqlite, threading, concurrent*
**Approach:** Using SQLite with multiple threads
**Why failed:** "database is locked" errors under load
**Learned:** Use WAL mode or switch to PostgreSQL for concurrent writes
```

## MCP Resources

Access failures directly via MCP resources:

```
@sage://failure/jwt-refresh-localstorage
```

## Auto-Injection

When starting a new session, Sage automatically injects relevant failures based on:

1. **Keywords** — Match failure keywords against session context
2. **Semantic similarity** — Embedding-based matching (if available)
3. **Recency** — Recent failures score higher

Configure injection:
```yaml
# .sage/tuning.yaml
failure_memory_enabled: true
failure_injection_limit: 3  # Max failures to inject
```

## Storage Location

```
.sage/failures/
├── 2026-02-15T10-30-00_jwt-refresh-localstorage.md
├── 2026-02-10T14-22-00_sqlite-multithread.md
└── 2026-02-08T09-15-00_cors-preflight.md
```

Filenames include timestamp for chronological sorting.

## Security

Failure IDs are sanitized to prevent path traversal:

```python
# Input: "../../../etc/passwd"
# Sanitized: "etc-passwd"
```

See [`sage/failures.py:96`](../../sage/failures.py) for `_sanitize_id()`.

## Implementation

| Function | Purpose | Location |
|----------|---------|----------|
| `save_failure()` | Record a new failure | [`failures.py:187`](../../sage/failures.py) |
| `load_failures()` | Load all failures | [`failures.py:255`](../../sage/failures.py) |
| `recall_failures()` | Semantic recall | [`failures.py:282`](../../sage/failures.py) |
| `format_failure_for_context()` | Format for injection | [`failures.py:486`](../../sage/failures.py) |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `failure_memory_enabled` | `true` | Enable failure memory |
| `failure_injection_limit` | `3` | Max failures to auto-inject |

## Best Practices

1. **Record immediately** — Capture failures when they happen, not later
2. **Be specific** — "XSS vulnerability via localStorage" not "security issue"
3. **Include learned** — Always document what to do instead
4. **Add keywords** — More keywords = better recall
5. **Link related** — Connect to relevant checkpoints/knowledge
