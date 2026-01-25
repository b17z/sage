"""Default Sage methodology skills.

These skills teach Claude HOW to use Sage effectively.
Installed via `sage skills install`.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from sage.config import SKILLS_DIR


def _sanitize_skill_name(name: str) -> str:
    """Sanitize a skill name to prevent path traversal attacks.

    Removes any characters that could be used for directory traversal
    or shell injection. Only allows alphanumeric, underscore, and hyphen.
    """
    # Remove any path separators and dangerous characters
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")
    return sanitized or "unnamed"

# Sage skills live in ~/.claude/skills/sage/
SAGE_SKILLS_DIR = SKILLS_DIR / "sage"


@dataclass(frozen=True)
class DefaultSkill:
    """A default Sage skill definition."""

    name: str
    content: str


SAGE_MEMORY_SKILL = DefaultSkill(
    name="sage-memory",
    content='''---
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
''',
)


SAGE_RESEARCH_SKILL = DefaultSkill(
    name="sage-research",
    content='''---
name: sage-research
description: Research methodology - when and how to checkpoint with Sage
triggers: [research, synthesis, hypothesis, conclude, investigation, summarize, therefore, branch point]
author: sage
version: 1.0.0
---

# Sage Research Methodology

Checkpoint at **state transitions**, not token pressure.

## When to Checkpoint

| Trigger | Signal | Confidence |
|---------|--------|------------|
| `synthesis` | "Therefore...", "In summary...", "The answer is..." | 0.5+ |
| `web_search_complete` | After processing search results | 0.3+ |
| `branch_point` | "We could either X or Y..." | 0.4+ |
| `constraint_discovered` | "This won't work because..." | 0.4+ |
| `topic_shift` | Conversation changing direction | 0.4+ |
| `manual` | User says "checkpoint" or "save this" | 0.0 (always) |

## The Research Workflow

```
WebSearch → synthesize findings → sage_autosave_check → respond to user
```

**A research task is NOT complete until `sage_autosave_check` is called.**

## What to Capture

```python
sage_autosave_check(
    trigger_event="synthesis",           # What triggered this
    core_question="What are we solving?", # The driving question
    current_thesis="Our current position", # 1-2 sentence synthesis
    confidence=0.7,                       # How confident (0-1)
    open_questions=["What's still unknown?"],
    key_evidence=["Concrete facts supporting thesis"],
)
```

## Responding to Hook Detections

When you see these messages from hooks, act immediately:

- 🔍 **Synthesis detected** → `sage_autosave_check(trigger_event='synthesis', ...)`
- 🔀 **Branch point detected** → `sage_autosave_check(trigger_event='branch_point', ...)`
- 🚧 **Constraint discovered** → `sage_autosave_check(trigger_event='constraint_discovered', ...)`
- ↪️ **Topic shift detected** → `sage_autosave_check(trigger_event='topic_shift', ...)`

**Never ignore hook detection messages.** They indicate checkpoint-worthy moments.

## Before Changing Topics

Always checkpoint before moving to a new subject:

```python
sage_autosave_check(
    trigger_event="topic_shift",
    core_question="Previous topic question",
    current_thesis="Where we landed",
    confidence=0.6,
)
```

## Saving Reusable Knowledge

When you learn something worth remembering across sessions:

```python
sage_save_knowledge(
    knowledge_id="kebab-case-id",
    content="The insight in markdown",
    keywords=["trigger", "words", "for", "recall"],
)
```

## Recalling Knowledge

Before starting work, check what's already known:

```python
sage_recall_knowledge(query="what you're working on")
```
''',
)


SAGE_SESSION_SKILL = DefaultSkill(
    name="sage-session",
    content='''---
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
''',
)


SAGE_KNOWLEDGE_HYGIENE_SKILL = DefaultSkill(
    name="sage-knowledge-hygiene",
    content='''---
name: sage-knowledge-hygiene
description: Evaluate and maintain knowledge freshness - detect and fix stale knowledge
triggers: [stale knowledge, outdated, knowledge recalled, update knowledge, deprecated, freshness, knowledge hygiene]
author: sage
version: 1.0.0
---

# Knowledge Hygiene

When knowledge is recalled, evaluate its freshness. Stale knowledge injects wrong context.

## Staleness Signals

| Signal | How to Detect | Example |
|--------|---------------|---------|
| **Version mismatch** | Knowledge mentions old version | "Post v2.4" when we're on v2.6 |
| **Temporal markers** | "TODO", "planned", "upcoming", "will be" | Feature listed as TODO but shipped |
| **Contradiction** | Recalled content conflicts with current facts | "Not implemented" but we just used it |
| **Date references** | Specific dates in the past | "Q1 2025 roadmap" |

## Type-Specific Evaluation

Different knowledge types decay differently:

| Type | Decay Rate | Evaluate For |
|------|------------|--------------|
| `knowledge` | Medium | Version refs, temporal markers, contradictions |
| `preference` | Very slow | Only explicit user contradiction |
| `todo` | Fast | Completion, age without action (30+ days) |
| `reference` | Slow | Source validity, version refs |

## When to Evaluate

1. **On recall** - Quick scan when knowledge is surfaced
2. **Session start** - Review proactively recalled items
3. **After version bump** - Check for version-specific knowledge
4. **Explicit request** - User asks to review knowledge

## Remediation Actions

### If content is wrong/outdated:
```python
sage_update_knowledge(
    knowledge_id="the-id",
    content="Updated accurate content",
)
```

### If superseded but worth keeping for history:
```python
sage_deprecate_knowledge(
    knowledge_id="the-id",
    reason="Superseded by v2.6 skills architecture",
    replacement_id="new-knowledge-id",  # optional
)
```

### If no longer relevant:
```python
sage_archive_knowledge(knowledge_id="the-id")
```

### If still valid (bump freshness):
```python
sage_update_knowledge(
    knowledge_id="the-id",
    content=None,  # Keep content
    # Just accessing it updates last_recalled internally
)
```

## Quick Hygiene Check

When you see recalled knowledge, ask:

1. **Version check**: Does it reference an old version?
2. **Completion check**: Does it list something as TODO that's done?
3. **Contradiction check**: Does it conflict with what we know now?

If any answer is yes → remediate immediately.

## Example: Stale Feature List

Recalled knowledge says:
> "Post v2.4.0 - TODO: Proactive recall on session start"

But we're on v2.6 and proactive recall shipped in v2.5.

**Action:**
```python
sage_update_knowledge(
    knowledge_id="feature-ideas",
    content="Updated content marking proactive recall as shipped...",
)
```
''',
)


# All default skills
DEFAULT_SKILLS = [
    SAGE_MEMORY_SKILL,
    SAGE_RESEARCH_SKILL,
    SAGE_SESSION_SKILL,
    SAGE_KNOWLEDGE_HYGIENE_SKILL,
]


def get_skill_path(skill_name: str) -> Path:
    """Get the path where a Sage skill should be installed.

    Security: skill_name is sanitized to prevent path traversal.
    """
    safe_name = _sanitize_skill_name(skill_name)
    return SAGE_SKILLS_DIR / safe_name / "SKILL.md"


def install_skill(skill: DefaultSkill, force: bool = False) -> tuple[bool, str]:
    """Install a single skill.

    Returns:
        (success, message) tuple
    """
    skill_dir = SAGE_SKILLS_DIR / skill.name
    skill_path = skill_dir / "SKILL.md"

    if skill_path.exists() and not force:
        return False, f"Skill '{skill.name}' already exists (use --force to overwrite)"

    # Create directory and write skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(skill.content)

    # Set restrictive permissions (0o644 for skill files - readable but not world-writable)
    skill_path.chmod(0o644)

    action = "Updated" if skill_path.exists() else "Installed"
    return True, f"{action} {skill.name}"


def install_all_skills(force: bool = False) -> list[tuple[str, bool, str]]:
    """Install all default Sage skills.

    Returns:
        List of (skill_name, success, message) tuples
    """
    results = []
    for skill in DEFAULT_SKILLS:
        success, message = install_skill(skill, force=force)
        results.append((skill.name, success, message))
    return results


def get_installed_sage_skills() -> list[str]:
    """List installed Sage methodology skills."""
    if not SAGE_SKILLS_DIR.exists():
        return []

    skills = []
    for skill_dir in SAGE_SKILLS_DIR.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            skills.append(skill_dir.name)

    return sorted(skills)


def check_skill_version(skill_name: str) -> tuple[str | None, str | None]:
    """Check installed vs available version for a skill.

    Security: skill_name is sanitized to prevent path traversal.

    Returns:
        (installed_version, available_version) tuple
    """
    safe_name = _sanitize_skill_name(skill_name)
    skill_path = SAGE_SKILLS_DIR / safe_name / "SKILL.md"

    # Get installed version
    installed_version = None
    if skill_path.exists():
        content = skill_path.read_text()
        match = re.search(r"version:\s*([^\n]+)", content)
        if match:
            installed_version = match.group(1).strip()

    # Get available version from defaults
    available_version = None
    for skill in DEFAULT_SKILLS:
        if skill.name == skill_name:
            match = re.search(r"version:\s*([^\n]+)", skill.content)
            if match:
                available_version = match.group(1).strip()
            break

    return installed_version, available_version
