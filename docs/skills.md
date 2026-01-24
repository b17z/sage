# Sage Skills Architecture

Sage uses Claude Skills to teach Claude **how** to use Sage effectively, while keeping CLAUDE.md lean. This document explains the architecture and how to extend it.

## The Split

| Layer | Role | When Loaded |
|-------|------|-------------|
| **CLAUDE.md** | Project basics, tool reference | Always |
| **Skills** | Methodology, workflows | On-demand |
| **MCP** | Memory storage (checkpoints, knowledge) | Always |

**The rule of thumb:** If you're explaining how to do something, that's a skill. If you need Claude to access something, that's MCP.

## Default Sage Skills

Sage ships three methodology skills, installed via `sage skills install`:

### sage-memory

**Triggers:** checkpoint, save, autosave, knowledge

Teaches Claude the background Task pattern for Sage saves:

```markdown
When saving to Sage, use background Task to avoid blocking:

Task(subagent_type='general-purpose', model='haiku', run_in_background=true,
     prompt='Call [sage tool] with [params]. Return result.')

Never call sage_save_checkpoint or sage_save_knowledge directly.
```

### sage-research

**Triggers:** research, synthesis, hypothesis, conclude, investigation

Teaches Claude checkpoint methodology:

- **When to checkpoint:** synthesis moments, branch points, topic shifts
- **What to capture:** core_question, thesis, confidence, open_questions
- **Research workflow:** WebSearch → synthesize → sage_autosave_check → respond
- **Hook responses:** How to respond to semantic detector hooks

### sage-session

**Triggers:** session start, beginning, hello, context check

Teaches Claude the session start ritual:

1. Call `sage_health()` to check continuity + proactive recall
2. Review pending todos with `sage_list_todos()`
3. Load relevant checkpoint if continuing work

## Installation

```bash
# Install default Sage skills
sage skills install

# Creates:
# ~/.claude/skills/sage/
# ├── sage-memory/SKILL.md
# ├── sage-research/SKILL.md
# └── sage-session/SKILL.md
```

## How It Works

1. Claude sees skill descriptions at session start (progressive disclosure)
2. When context matches triggers, Claude loads the skill
3. Skill instructions guide Claude's behavior
4. CLAUDE.md stays lean - just tool reference

```
┌─────────────────────────────────────────────────────────────┐
│                         Claude                              │
│         (sees skill descriptions, picks when relevant)      │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────┐
│     Sage Skills         │     │      Sage MCP               │
│  (methodology layer)    │     │   (memory layer)            │
│                         │     │                             │
│  - sage-memory          │────▶│  - sage_save_checkpoint     │
│  - sage-research        │     │  - sage_recall_knowledge    │
│  - sage-session         │     │  - sage_autosave_check      │
│                         │     │  - ...                      │
└─────────────────────────┘     └─────────────────────────────┘
```

## Skill Locations

Skills follow the same cascade as config:

```
~/.claude/skills/sage/           # Installed via `sage skills install`
├── sage-memory/SKILL.md         # Default patterns
├── sage-research/SKILL.md
└── sage-session/SKILL.md

<project>/.claude/skills/sage/   # Project overrides (optional)
└── sage-research/SKILL.md       # Custom checkpoint triggers for this project
```

**Precedence:** Project > Personal > Sage Defaults

## Creating Custom Skills

You can extend Sage with domain-specific skills that incorporate Sage tools:

```markdown
# ~/.claude/skills/my-security-review/SKILL.md
---
name: my-security-review
description: Security review workflow with Sage memory
triggers: [security review, vulnerability, audit]
---

## Before reviewing code:
1. `sage_recall_knowledge(query="security principles OWASP")`
2. Review recalled knowledge for relevant checklists

## After reviewing:
1. `sage_autosave_check(trigger_event="synthesis", ...)` for significant findings
2. `sage_save_knowledge(...)` for new patterns discovered
```

The skill carries both the **perspective** (how to think) and the **memory ritual** (what to save/recall).

## CLI Commands

```bash
sage skills install              # Install default Sage skills
sage skills list                 # Show installed skills (including Sage skills)
sage skills update               # Update to latest Sage skill versions
```

## Why Skills vs CLAUDE.md?

| Aspect | CLAUDE.md | Skills |
|--------|-----------|--------|
| Loading | Always | On-demand |
| Token cost | Fixed overhead | Pay for what you use |
| Context | Competes with everything | Loads when relevant |
| Updates | Edit file | `sage skills update` |

**The insight:** Progressive disclosure. Instructions load when context matches, not every session.

## Token Efficiency

From [DEV Community](https://dev.to/jimquote/claude-skills-vs-mcp-complete-guide-to-token-efficient-ai-agent-architecture-4mkf):

> Skills use progressive disclosure — only pay for what you use. MCP definitions are always loaded — keep them concise.

Before (CLAUDE.md ~335 lines, always loaded):
- Session ritual: ~50 lines
- Research methodology: ~60 lines
- Background operations: ~25 lines
- **Total methodology overhead: ~135 lines every session**

After (Skills load on-demand):
- CLAUDE.md: ~200 lines (tool reference only)
- Skills: Load only when context matches triggers
- **Most sessions: 0 extra tokens for methodology**

## Relationship with Research Skills

Sage has two types of skills:

1. **Methodology skills** (this document): Teach how to use Sage
   - `sage-memory`, `sage-research`, `sage-session`
   - Installed via `sage skills install`

2. **Research skills**: Domain expertise personas
   - Created via `sage create <name>`
   - Have their own docs, history, shared memory
   - Use Sage for persistence

Both types can coexist. Research skills can reference methodology skills' patterns.

## Sources

- [Claude Blog: Extending capabilities with Skills and MCP](https://claude.com/blog/extending-claude-capabilities-with-skills-mcp-servers)
- [Claude Blog: Skills Explained](https://claude.com/blog/skills-explained)
- [IntuitionLabs: Skills vs MCP Comparison](https://intuitionlabs.ai/articles/claude-skills-vs-mcp)
- [Armin Ronacher: Skills vs Dynamic MCP Loadouts](https://lucumr.pocoo.org/2025/12/13/skills-vs-mcp/)
- [DEV Community: Token-Efficient AI Agent Architecture](https://dev.to/jimquote/claude-skills-vs-mcp-complete-guide-to-token-efficient-ai-agent-architecture-4mkf)
- [gend.co: Skills and CLAUDE.md Guide](https://www.gend.co/blog/claude-skills-claude-md-guide)
