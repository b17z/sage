---
name: sage-memory
description: Background save pattern for Sage operations - prevents blocking
triggers: [checkpoint, save knowledge, autosave, sage_save, persist, remember this]
author: sage
version: 1.0.0
---

# Sage Memory Operations

When saving to Sage (checkpoints or knowledge), **always use a background Task** to avoid blocking the conversation for 2-5 seconds.

## The Pattern

```
Task(subagent_type='general-purpose', model='haiku', run_in_background=true,
     prompt='Call sage_save_checkpoint with core_question="...", thesis="...", confidence=0.X, trigger="...". Return the result.')
```

## When This Applies

Use background Task for these MCP tools:
- `sage_save_checkpoint` - Full research checkpoint
- `sage_save_knowledge` - Persist reusable insight
- `sage_autosave_check` - Auto-checkpoint at breakpoints

## Why

These operations generate embeddings (2-5 seconds). Running them directly blocks the conversation. The background Task pattern:
1. Returns immediately with task ID
2. Subagent handles the save
3. You get notified when complete

## Never Do This

```
# WRONG - blocks conversation
sage_save_checkpoint(core_question="...", thesis="...", confidence=0.8)
```

## Always Do This

```
# RIGHT - non-blocking
Task(subagent_type='general-purpose', model='haiku', run_in_background=true,
     prompt='Call sage_save_checkpoint(...). Return result.')
```
