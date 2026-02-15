# MCP Resources (v4.0)

Access Sage data directly using `@sage://` syntax in Claude Code, without tool calls.

## Overview

MCP resources expose Sage data as mentionable entities:

```
@sage://system/objective.md      # System folder file
@sage://checkpoint/jwt-research  # Checkpoint by ID
@sage://knowledge/auth-patterns  # Knowledge item
@sage://failure/jwt-localstorage # Failure record
```

This is faster than tool calls for direct data access.

## Resource Types

### System Files

```
@sage://system/{filename}
```

Access files from `.sage/system/`:

```
@sage://system/objective.md
@sage://system/constraints.md
@sage://system/pinned/reference.md
```

### Checkpoints

```
@sage://checkpoint/{id}
```

Load a checkpoint by full or partial ID:

```
@sage://checkpoint/jwt-research
@sage://checkpoint/auth-2026-02
```

Returns the formatted checkpoint content.

### Knowledge

```
@sage://knowledge/{id}
```

Load a knowledge item:

```
@sage://knowledge/auth-patterns
@sage://knowledge/usdc-compliance
```

Returns the knowledge content with metadata and code links.

### Failures

```
@sage://failure/{id}
```

Load a failure record:

```
@sage://failure/jwt-localstorage
@sage://failure/sqlite-threading
```

Returns the failure with approach, why it failed, and what was learned.

## Usage in Claude Code

In your conversation with Claude:

```
Look at @sage://system/objective.md and help me with the next step.

Based on @sage://checkpoint/jwt-research, should we use cookies or localStorage?

Don't make the same mistake - see @sage://failure/jwt-localstorage
```

## Security

All resource access is secured:

### Path Validation

```python
def _validate_sage_path(path: str) -> str | None:
    # Block path traversal
    if ".." in path or path.startswith("/"):
        return None

    # Allow only safe characters
    if not re.match(r"^[a-zA-Z0-9_\-./]+$", path):
        return None

    return path.strip("/")
```

### Containment

System file resources verify the resolved path is within `.sage/system/`:

```python
file_path = file_path.resolve()
if system_folder.resolve() not in file_path.parents:
    return "File not in system folder"
```

See [`sage/mcp_server.py:2821`](../../sage/mcp_server.py) for the full implementation.

## Implementation

| Resource | Function | Location |
|----------|----------|----------|
| `sage://system/{filename}` | `get_system_file_resource()` | [`mcp_server.py:2850`](../../sage/mcp_server.py) |
| `sage://checkpoint/{id}` | `get_checkpoint_resource()` | [`mcp_server.py:2889`](../../sage/mcp_server.py) |
| `sage://knowledge/{id}` | `get_knowledge_resource()` | [`mcp_server.py:2916`](../../sage/mcp_server.py) |
| `sage://failure/{id}` | `get_failure_resource()` | [`mcp_server.py:2960`](../../sage/mcp_server.py) |

## Error Handling

Resources return error messages (not exceptions) for:

- Invalid paths (traversal attempts)
- Missing files
- Parse errors

```
# Example error responses
"Invalid filename: ../etc/passwd"
"Checkpoint not found: nonexistent"
"File not in system folder: ../config.yaml"
```

## Resources vs Tools

| Aspect | Resources (`@sage://`) | Tools (`sage_*()`) |
|--------|------------------------|-------------------|
| Syntax | `@sage://system/file.md` | `sage_load_checkpoint(id)` |
| Context injection | Automatic on session start | Requires explicit call |
| Search | No (direct ID only) | Yes (semantic search) |
| Side effects | Read-only | Can save/modify |
| Best for | Quick lookups | Complex operations |

## Best Practices

1. **Use resources for quick lookups** — When you know exactly what you want
2. **Use tools for search** — When you need semantic matching
3. **Combine both** — Search with tool, then reference with resource
4. **Reference in prompts** — `@sage://` syntax works inline

## Example Workflow

```
1. Claude uses sage_search_checkpoints("jwt auth")
2. Finds checkpoint ID: "jwt-research-2026-02-15"
3. User references: "Based on @sage://checkpoint/jwt-research-2026-02-15..."
4. Claude gets full checkpoint without another tool call
```
