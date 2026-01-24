# Sage Integration for CLAUDE.md

Copy this into your project's CLAUDE.md to enable automatic memory and checkpointing.

---

## Sage Memory System

You have access to Sage MCP tools for persistent memory across sessions.

### Session Start
Call `sage_health()` at the start of meaningful work to:
- Check for continuity context from previous sessions
- Verify the memory system is working

### After Web Searches
**REQUIRED:** After completing a web search and synthesizing results, call:
```
sage_autosave_check(
  trigger_event="web_search_complete",
  core_question="<what you were researching>",
  current_thesis="<your synthesized findings>",
  confidence=<0.0-1.0>
)
```

### When Reaching Conclusions
When you use phrases like "therefore", "in summary", "the answer is", call:
```
sage_autosave_check(
  trigger_event="synthesis",
  core_question="<the question answered>",
  current_thesis="<the conclusion>",
  confidence=<0.0-1.0>
)
```

### Before Topic Changes
Before shifting to a new topic, checkpoint the current one:
```
sage_autosave_check(
  trigger_event="topic_shift",
  core_question="<previous topic>",
  current_thesis="<where you left off>",
  confidence=<0.0-1.0>
)
```

### Saving Knowledge
When you learn something reusable about this project, save it:
```
sage_save_knowledge(
  knowledge_id="<kebab-case-id>",
  content="<the insight>",
  keywords=["keyword1", "keyword2"]
)
```

### Recalling Knowledge
Before starting work on a topic, check for existing knowledge:
```
sage_recall_knowledge(query="<what you're working on>")
```
