# Knowledge Linking (v4.0)

Connect related knowledge items for multi-hop reasoning. When Claude recalls one item, linked items are shown too.

## Overview

Knowledge items often relate to each other:

```
auth-patterns ←─ related ─→ jwt-security
      │
      └── extends ──→ oauth-integration
```

Sage v4.0 lets you create these links explicitly.

## Link Types

| Relation | Meaning | Example |
|----------|---------|---------|
| `related` | General connection | auth-patterns ↔ session-management |
| `supersedes` | This replaces that | jwt-v2 → jwt-v1 |
| `contradicts` | These conflict | rest-polling ↔ websocket-approach |
| `extends` | This builds on that | oauth-integration → auth-patterns |

## Creating Links

### MCP Tool

```python
sage_link_knowledge(
    source_id="auth-patterns",
    target_id="jwt-security",
    relation="related",  # related | supersedes | contradicts | extends
    note="Both cover authentication best practices",
    bidirectional=True   # Create reverse link too
)
```

### Bidirectional Links

With `bidirectional=True`:
- Creates `auth-patterns → jwt-security`
- Also creates `jwt-security → auth-patterns`

## Knowledge Item Links

Knowledge items can have links stored in their YAML frontmatter:

```yaml
# .sage/knowledge/auth-patterns.md
---
id: auth-patterns
knowledge_links:
  - target_id: jwt-security
    relation: related
    note: "Both cover auth best practices"
  - target_id: oauth-integration
    relation: extends
    note: "OAuth builds on these patterns"
---
```

## Recall Behavior

When recalling `auth-patterns`, linked items are shown:

```markdown
## auth-patterns
...content...

### Linked Items
- **jwt-security** [related] — Both cover auth best practices
- **oauth-integration** [extends] — OAuth builds on these patterns
```

## Checkpoint Links

Checkpoints can also link to knowledge and other checkpoints:

```yaml
# Checkpoint fields
continues_from: "jwt-research-phase1"  # Chain of research
related_knowledge:
  - "auth-patterns"
  - "jwt-security"
```

This creates a research trail:

```
jwt-research-phase1
    → jwt-research-phase2
        → jwt-research-final
```

## Implementation

| Function | Purpose | Location |
|----------|---------|----------|
| `link_knowledge()` | Create a link | [`knowledge.py`](../../sage/knowledge.py) |
| `get_linked_knowledge()` | Get linked items | [`knowledge.py`](../../sage/knowledge.py) |
| `KnowledgeLink` dataclass | Link structure | [`knowledge.py`](../../sage/knowledge.py) |

### KnowledgeLink Structure

```python
@dataclass(frozen=True)
class KnowledgeLink:
    target_id: str           # ID of linked item
    relation: str = "related"  # related | supersedes | contradicts | extends
    note: str = ""           # Why this link exists
```

## Use Cases

### 1. Supersession
When knowledge becomes outdated but you want to preserve history:

```python
sage_link_knowledge(
    source_id="jwt-v2-patterns",
    target_id="jwt-v1-patterns",
    relation="supersedes",
    note="v2 handles refresh tokens differently"
)
```

### 2. Research Chains
Track how research builds on itself:

```python
# Checkpoint linking
sage_save_checkpoint(
    core_question="How should we implement OAuth?",
    thesis="Use PKCE flow for SPAs",
    continues_from="auth-research-phase1",
    related_knowledge=["auth-patterns", "oauth-spec"]
)
```

### 3. Conflict Documentation
Document when approaches conflict:

```python
sage_link_knowledge(
    source_id="rest-polling-approach",
    target_id="websocket-approach",
    relation="contradicts",
    note="REST polling vs WebSockets - can't use both"
)
```

## Best Practices

1. **Use bidirectional for `related`** — If A relates to B, B relates to A
2. **Use unidirectional for `supersedes`** — Old doesn't supersede new
3. **Add notes** — Explain *why* things are linked
4. **Link checkpoints to knowledge** — Connect research to reusable insights
5. **Chain related checkpoints** — Use `continues_from` for research sessions
