---
name: sage-session
description: Session start ritual - continuity and context injection
triggers: [session start, beginning, hello, good morning, context check, new session, starting fresh]
author: sage
version: 1.0.0
---

# Sage Session Start

On session start, Sage automatically injects context. Here's how to use it.

## Automatic Injection (v2.5+)

On your **first Sage tool call** each session, Sage automatically injects:
- **Continuity context** from previous compacted sessions
- **Proactive recall** of knowledge relevant to this project

This happens automatically when you call `sage_health()`, `sage_version()`, `sage_list_knowledge()`, etc.

## Recommended: Call sage_health()

```python
sage_health()
```

This:
1. Checks Sage is working
2. Injects any pending continuity context
3. Surfaces proactively recalled knowledge
4. Shows system diagnostics

## If Continuing Previous Work

After `sage_health()`, load a relevant checkpoint:

```python
sage_search_checkpoints(query="what you're continuing")
sage_load_checkpoint(checkpoint_id="...")
```

## Check Pending Todos

```python
sage_list_todos()
```

Review any persistent reminders from previous sessions.

## The Flow

```
1. sage_health()           # Context injection + diagnostics
2. sage_list_todos()       # Check reminders (optional)
3. sage_load_checkpoint()  # Restore deep context (if needed)
4. Begin work
```
