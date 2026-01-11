# Skill Authoring Best Practices

Lessons learned from building and testing Claude Code Agent Skills.

## How Skills Work

1. **At session start**: Claude loads skill **names and descriptions** into context
2. **During conversation**: Claude matches user requests to skill descriptions
3. **When matched**: Claude reads the full SKILL.md content
4. **Execution**: Claude follows the skill instructions

**Key insight**: The `description` field is the routing key. Claude doesn't read full skill content until it decides the skill is relevant based on the description match.

## Description Field (Critical)

The description determines whether Claude invokes your skill. Vague descriptions fail.

### Bad Description
```yaml
description: Semantic checkpointing for research and complex tasks
```
❌ Too vague. Claude can't match this to specific user requests.

### Good Description (WHEN + WHEN NOT Pattern)
```yaml
description: >
  Auto-save research progress using sage_autosave_check MCP tool.
  INVOKE WHEN: user asks to research, compare, analyze, or investigate topics;
  after completing web searches; when synthesizing conclusions.
  INVOKE FOR: checkpoint, save this, remember this.
  DO NOT INVOKE: for simple Q&A, code editing, or file operations.
```
✅ Explicit triggers, action verbs, clear boundaries.

### Description Checklist
- [ ] Includes action verbs (research, compare, analyze, create)
- [ ] Lists specific trigger phrases users might say
- [ ] Specifies WHEN to invoke
- [ ] Specifies WHEN NOT to invoke (prevents false positives)
- [ ] Mentions MCP tools the skill uses (helps Claude connect skill → tools)
- [ ] Under 1024 characters (Claude's limit)

## Skills vs MCP: The Division

From official docs: *"Skills tell Claude how to use tools; MCP provides the tools."*

| Layer | Purpose | Example |
|-------|---------|---------|
| **MCP** | Provides callable tools | `sage_autosave_check` function |
| **Skill** | Teaches when/how to use tools | "Call after web search with confidence > 0.5" |

Skills without MCP: Claude knows *what* to do but can't *execute*
MCP without Skills: Claude has tools but doesn't know *when* to use them

## Auto-Invoke vs Manual Invoke

Skills can be:
- **Auto-invoked**: Claude decides based on description matching
- **Manually invoked**: User types `/skill-name` or asks explicitly

The `auto_invoke: true` frontmatter enables auto-invocation, but **description quality determines whether it actually fires**.

## Frontmatter Fields

```yaml
---
name: skill-name              # Required: kebab-case identifier
description: >                # Required: THE ROUTING KEY
  Detailed description with
  INVOKE WHEN and INVOKE FOR patterns.
auto_invoke: true             # Optional: enable auto-invocation
allowed-tools: "Read,Bash"    # Optional: restrict tool access
model: "inherit"              # Optional: model override
---
```

Note: `triggers:` field in frontmatter appears in some examples but isn't documented as functional. Rely on the `description` instead.

## Skill Content Structure

After the frontmatter, structure content for progressive disclosure:

1. **Summary** (first paragraph) — What this skill does
2. **When to Use** — Specific scenarios (reinforces description)
3. **How to Use** — Step-by-step, tool call examples
4. **Reference** — Schemas, formats, detailed docs

Keep SKILL.md under 500 lines. Use separate reference files for details.

## Testing Skills

1. Start fresh Claude Code session (skills load at startup)
2. Ask: "What skills are available?" — verify your skill appears
3. Ask: "What does the [skill-name] skill tell you to do?" — verify content loads
4. Test with a matching request — verify auto-invocation
5. If not auto-invoking, improve description specificity

## Common Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| Skill not auto-invoking | Vague description | Add WHEN/WHEN NOT pattern |
| Skill invoked but no action | Missing MCP tools | Add MCP server with tools |
| Tool available but not called | Skill doesn't mention tool | Add tool name to skill content |
| Works once, stops working | Context drift in long sessions | Keep skill instructions concise |

## Claude Prioritization Behavior (Important Finding)

Claude optimizes for **task completion over procedural compliance**.

When given standing orders like "after web search, call autosave tool":
- ✅ Claude reads and understands the instruction
- ✅ Claude knows what it should do
- ❌ Claude deprioritizes procedural side-effects when focused on main task

Claude's own explanation: *"I got focused on synthesizing the answer and didn't treat the autosave as a mandatory post-search step."*

### Implications for Skill Design

| Instruction Type | Reliability | Example |
|------------------|-------------|----------|
| Part of main task | High | "Research X and format as table" |
| Procedural side-effect | Low | "After researching, also call autosave" |
| When reminded | High | "You forgot to autosave" → Claude does it |

### Claude's Priority Hierarchy (from Claude itself)

| Priority | Pattern | Example |
|----------|---------|----------|
| Highest | Explicit prohibitions | "NEVER push without asking" |
| High | Direct user request | "Research X vs Y" |
| Medium | Workflow enhancements | "Use autosave after searches" |
| Lower | Recommendations | "Consider using..." |

### Making Procedural Steps Mandatory

Claude's suggested patterns for elevating priority:

**1. Completion checklist (most effective):**
```markdown
## Task Completion (REQUIRED)
A research task is NOT complete until:
1. ✅ Answer provided
2. ✅ `tool_call` executed

**NEVER skip step 2.**
```

**2. Inline workflow:**
```
Workflow: WebSearch → synthesize → sage_autosave_check → respond
```

**3. Avoid section segregation:**
- ❌ Separate "## Autosave" section (reads as supplementary)
- ✅ Integrate into main workflow section (reads as required)

### Other Approaches

1. **Use hooks**: Claude Code hooks trigger automatically, not dependent on Claude's decision
2. **Accept reminder pattern**: When reminded, Claude complies reliably
3. **Explicit invocation**: User or slash command triggers the action

## References

- [Official Skills Docs](https://code.claude.com/docs/en/skills)
- [Agent Skills Overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Skill Description Best Practices](https://docs.claude.com/en/docs/agent-sdk/skills)
