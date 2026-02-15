---
description: Manage the knowledge base - add, list, update, deprecate
---

# /knowledge

Manage stored knowledge items - durable insights useful across sessions.

## Usage

```
/knowledge [list|add|update|deprecate|archive|remove]
```

## Subcommands

### List all knowledge
```
/knowledge list
```
Shows all knowledge items with IDs, keywords, and status.

### Add new knowledge
```
/knowledge add
```
Save a new insight. You'll provide:
- ID (kebab-case identifier)
- Content (the insight itself)
- Keywords (trigger words for recall)

### Update existing
```
/knowledge update <id>
```
Modify content or keywords of an existing item.

### Mark as outdated
```
/knowledge deprecate <id>
```
Flag knowledge as outdated (still visible but shows warning).

### Hide from recall
```
/knowledge archive <id>
```
Remove from active recall without deleting.

### Delete permanently
```
/knowledge remove <id>
```
Permanently delete a knowledge item.

## Implementation

Map subcommands to MCP tools:
- `list` → `sage_list_knowledge()`
- `add` → `sage_save_knowledge(id, content, keywords)`
- `update <id>` → `sage_update_knowledge(id, ...)`
- `deprecate <id>` → `sage_deprecate_knowledge(id, reason)`
- `archive <id>` → `sage_archive_knowledge(id)`
- `remove <id>` → `sage_remove_knowledge(id)`

## Output Format

```markdown
## Knowledge Base

| ID | Keywords | Status |
|----|----------|--------|
| jwt-auth-pattern | jwt, authentication, tokens | active |
| rate-limiting | security, login, rate-limit | active |
| old-api-format | api, legacy | deprecated |

**3 items** (2 active, 1 deprecated)
```

## What to Store

| Type | Example |
|------|---------|
| Research conclusions | "GDPR Article 6 requires explicit consent for AI training" |
| Validated decisions | "We chose PostgreSQL over MongoDB because..." |
| Domain expertise | API patterns, regulatory summaries, technical constraints |
| User preferences | "Prefers academic sources", "Wants concise answers" |
| Project context | Tech stack, architecture decisions, constraints |
