# MCP Auto-Checkpoint Design

## Problem

The checkpoint skill tells Claude *when* and *what* to checkpoint, but Claude has no way to actually persist the checkpoint. The user must manually copy YAML output and run CLI commands.

**Current flow (manual):**
```
Claude detects synthesis → outputs YAML → user copies → sage checkpoint save
```

**Desired flow (automatic):**
```
Claude detects synthesis → calls save_checkpoint tool → done
```

---

## Solution: MCP Server

[Model Context Protocol (MCP)](https://modelcontextprotocol.io/) allows Claude to call external tools. We build an MCP server that exposes Sage operations as tools Claude can invoke directly.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Claude Code                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │ Checkpoint  │    │ Knowledge   │    │   User      │ │
│  │   Skill     │    │   Skill     │    │   Query     │ │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘ │
│         │                  │                  │        │
│         ▼                  ▼                  ▼        │
│  ┌─────────────────────────────────────────────────┐   │
│  │              MCP Tool Calls                      │   │
│  │  save_checkpoint(), recall_knowledge(), etc.     │   │
│  └──────────────────────┬──────────────────────────┘   │
└─────────────────────────┼──────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  Sage MCP Server                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │ checkpoint  │    │ knowledge   │    │   skill     │ │
│  │   tools     │    │   tools     │    │   tools     │ │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘ │
└─────────┼───────────────────┼───────────────────┼──────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│                    ~/.sage/                             │
│  checkpoints/    knowledge/    skills/    config.yaml   │
└─────────────────────────────────────────────────────────┘
```

---

## MCP Tools

### Checkpoint Tools

#### `save_checkpoint`
Save a semantic checkpoint.

**Input:**
```json
{
  "core_question": "string",
  "thesis": "string",
  "confidence": 0.0-1.0,
  "trigger": "synthesis | branch_point | constraint | transition | manual",
  "open_questions": ["string"],
  "sources": [
    {
      "id": "string",
      "type": "person | document | code | api | observation",
      "take": "string",
      "relation": "supports | contradicts | nuances"
    }
  ],
  "tensions": [
    {
      "between": ["source1", "source2"],
      "nature": "string",
      "resolution": "unresolved | resolved | moot"
    }
  ],
  "unique_contributions": [
    {
      "type": "discovery | experiment | synthesis",
      "content": "string"
    }
  ],
  "action": {
    "goal": "string",
    "type": "decision | implementation | learning | exploration"
  }
}
```

**Output:**
```json
{
  "checkpoint_id": "2026-01-10T23-45-00_thesis-slug",
  "path": "/Users/x/.sage/checkpoints/2026-01-10T23-45-00_thesis-slug.yaml"
}
```

#### `list_checkpoints`
List saved checkpoints.

**Input:**
```json
{
  "limit": 10,
  "skill": "optional-skill-filter"
}
```

**Output:**
```json
{
  "checkpoints": [
    {
      "id": "string",
      "thesis": "string (truncated)",
      "confidence": 0.75,
      "trigger": "synthesis",
      "saved": "2026-01-10T23:45:00"
    }
  ]
}
```

#### `load_checkpoint`
Load a checkpoint for context injection.

**Input:**
```json
{
  "checkpoint_id": "string or partial match"
}
```

**Output:**
```json
{
  "checkpoint": { /* full checkpoint object */ },
  "formatted_context": "# Research Context (Restored)..."
}
```

### Knowledge Tools

#### `save_knowledge`
Save an insight to the knowledge base.

**Input:**
```json
{
  "id": "string",
  "content": "string (markdown)",
  "keywords": ["string"],
  "skill": "optional-skill-scope",
  "source": "optional source description"
}
```

#### `recall_knowledge`
Recall relevant knowledge for a query.

**Input:**
```json
{
  "query": "string",
  "skill": "current-skill"
}
```

**Output:**
```json
{
  "items": [
    {
      "id": "string",
      "content": "string",
      "source": "string",
      "tokens": 83
    }
  ],
  "total_tokens": 83,
  "formatted_context": "📚 Recalled Knowledge..."
}
```

---

## Implementation

### Option A: Python MCP Server (Recommended)

Use the official `mcp` Python package:

```python
# sage/mcp_server.py
from mcp.server import Server
from mcp.types import Tool, TextContent

from sage.checkpoint import save_checkpoint, create_checkpoint_from_dict
from sage.knowledge import add_knowledge, recall_knowledge

server = Server("sage")

@server.tool()
async def save_checkpoint_tool(
    core_question: str,
    thesis: str,
    confidence: float,
    trigger: str = "synthesis",
    open_questions: list[str] = [],
    sources: list[dict] = [],
    tensions: list[dict] = [],
    unique_contributions: list[dict] = [],
    action: dict = {},
) -> str:
    """Save a semantic checkpoint of current research state."""
    checkpoint = create_checkpoint_from_dict({
        "core_question": core_question,
        "thesis": thesis,
        "confidence": confidence,
        "open_questions": open_questions,
        "sources": sources,
        "tensions": tensions,
        "unique_contributions": unique_contributions,
        "action": action,
    }, trigger=trigger)
    
    path = save_checkpoint(checkpoint)
    return f"Saved checkpoint: {checkpoint.id}"

@server.tool()
async def recall_knowledge_tool(query: str, skill: str = "") -> str:
    """Recall relevant knowledge for the current query."""
    result = recall_knowledge(query, skill)
    if result.count == 0:
        return "No relevant knowledge found."
    return format_recalled_context(result)

# Run server
if __name__ == "__main__":
    server.run()
```

### Configuration

Add to Claude Code's MCP config (`~/.config/claude-code/mcp.json`):

```json
{
  "mcpServers": {
    "sage": {
      "command": "python",
      "args": ["-m", "sage.mcp_server"],
      "env": {}
    }
  }
}
```

---

## Auto-Checkpoint Flow

With MCP tools available, the checkpoint skill can actually execute:

### Updated `skills/checkpoint/SKILL.md`

```yaml
---
name: checkpoint
description: Semantic checkpointing with auto-save
auto_invoke: true
triggers:
  - synthesis moment detected
  - branch point identified
---

# Checkpoint Skill

You have access to the `save_checkpoint` tool. When you detect a checkpoint-worthy moment, call it directly.

## When to Checkpoint

[existing triggers...]

## How to Checkpoint

Instead of outputting YAML, call the tool:

\`\`\`
save_checkpoint(
  core_question="...",
  thesis="...",
  confidence=0.8,
  trigger="synthesis",
  ...
)
\`\`\`

The tool returns the checkpoint ID. Briefly confirm to user:
"Checkpointed: [thesis summary]"
```

---

## Auto-Recall Flow

Similarly, knowledge recall can be automatic:

### Updated `skills/knowledge/SKILL.md`

```yaml
---
name: knowledge
description: Automatic knowledge recall via MCP
auto_invoke: true
---

# Knowledge Skill

You have access to `recall_knowledge` tool. Call it at the start of research queries to check for relevant stored knowledge.

## Behavior

1. When user asks a research question, call `recall_knowledge(query, skill)`
2. If results returned, inject into your context
3. Proceed with response
```

---

## Dependencies

```toml
# pyproject.toml additions
[project.optional-dependencies]
mcp = [
    "mcp>=0.1.0",
]

[project.scripts]
sage-mcp = "sage.mcp_server:main"
```

---

## Implementation Plan

### Phase 1: Basic MCP Server
- [ ] Create `sage/mcp_server.py` with checkpoint tools
- [ ] Add `save_checkpoint`, `list_checkpoints`, `load_checkpoint`
- [ ] Test with Claude Code MCP config
- [ ] Update checkpoint skill to use tools

### Phase 2: Knowledge Tools
- [ ] Add `save_knowledge`, `recall_knowledge` tools
- [ ] Update knowledge skill to auto-recall via tool
- [ ] Test end-to-end flow

### Phase 3: Polish
- [ ] Add error handling and validation
- [ ] Add `--mcp` flag to sage CLI to run server
- [ ] Document MCP setup in README
- [ ] Consider stdio vs HTTP transport

---

## Open Questions

1. **Transport**: stdio (simpler, Claude Code default) vs HTTP (allows multiple clients)?
   - **Recommendation**: Start with stdio

2. **Auto-recall timing**: Call at start of every response or only for research queries?
   - **Recommendation**: Only when skill is active or keywords detected

3. **Notification verbosity**: How much should Claude say when auto-checkpointing?
   - **Recommendation**: Brief inline notification, not disruptive

4. **Conflict with manual**: If user says "checkpoint" should it use tool or output YAML?
   - **Recommendation**: Use tool if available, fall back to YAML

---

## References

- [MCP Python SDK](https://github.com/anthropics/mcp-python-sdk)
- [Claude Code MCP Docs](https://docs.anthropic.com/claude-code/mcp)
- [MCP Specification](https://spec.modelcontextprotocol.io/)
