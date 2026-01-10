---
description: Recall and display relevant stored knowledge
---

# /recall

Search the knowledge base and display relevant stored insights.

## Instructions

When the user invokes `/recall`, search the knowledge base for items matching:
1. The topic/keywords they specify
2. Context from the current conversation
3. The active skill (if any)

Display matching knowledge items with their metadata.

## Usage

```
/recall [topic]
```

## Examples

```
/recall gdpr
/recall api patterns
/recall                  # Recall based on current conversation context
```

## Output Format

```markdown
## 📚 Knowledge Recall

### gdpr-summary
*Source: Research session 2026-01-08 | Keywords: gdpr, privacy, consent*

[Content of the knowledge item]

---

### consent-patterns  
*Source: Legal review | Keywords: consent, user agreement*

[Content of the knowledge item]

---

**Recalled 2 items (~730 tokens)**
```

## If No Matches

```markdown
No stored knowledge matches "[topic]".

Available knowledge:
- gdpr-summary (keywords: gdpr, privacy, consent)
- api-patterns (keywords: api, rest, graphql)

Add knowledge with: `sage knowledge add <file> --id <id> --keywords <kw1,kw2>`
```

## Behavior

- Show all matching items with their content
- Include metadata (source, keywords, when added)
- Display total token count
- If no topic specified, infer from conversation context
