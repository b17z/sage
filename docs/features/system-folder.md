# System Folder (v4.0)

The system folder provides agent-managed pinned content that is automatically injected at session start. This enables persistent context without requiring explicit tool calls.

## Overview

Store objectives, constraints, and context in `.sage/system/` and they're automatically available to Claude at session start.

```
.sage/system/
├── objective.md      # Current goal (always first)
├── constraints.md    # "Don't do X" rules
├── context.md        # Background context
└── pinned/           # Pinned checkpoints/knowledge
    └── auth-patterns.md
```

## Usage

### Creating System Files

Place markdown files in your project's `.sage/system/` directory:

```bash
mkdir -p .sage/system
echo "# Current Objective\n\nBuild a secure authentication system using JWT." > .sage/system/objective.md
```

### Priority Order

Files are loaded in a specific priority order:

1. **`objective.md`** — Current goal (always first)
2. **`constraints.md`** — Rules and restrictions
3. **`pinned/*.md`** — Pinned items (alphabetical)
4. **Other `*.md` files** — Additional context (alphabetical)

This ensures your most critical context is always included first.

### Token Budget

The system folder respects a token budget (default: 2000 tokens). When files exceed the budget:

1. Priority files are loaded first
2. Content is truncated with a `... (truncated)` indicator
3. Lower-priority files are skipped if budget is exhausted

Configure via:
```yaml
# .sage/tuning.yaml
system_folder_max_tokens: 2000
system_folder_enabled: true
```

## Example Files

### objective.md
```markdown
# Sprint Objective

Build user authentication with:
- Email/password registration
- JWT tokens with refresh
- Password reset flow

Target: Complete by Friday
```

### constraints.md
```markdown
# Constraints

- **Security**: Never store passwords in plain text
- **UX**: Keep forms simple, minimal fields
- **Code**: Follow existing patterns in `src/auth/`
- **Don't**: Use localStorage for sensitive tokens
```

## MCP Resources

Access system files directly using the `@sage://` resource syntax:

```
@sage://system/objective.md
@sage://system/constraints.md
@sage://system/pinned/auth-patterns.md
```

This works in Claude Code's `@` mentions without needing a tool call.

## Security

System folder access includes security measures:

- **Path validation** — Blocks `..` traversal and absolute paths
- **Allowlist** — Only alphanumeric, dash, underscore, dot, slash characters
- **Containment** — Files must be within `.sage/system/`

See [`sage/system_context.py:44`](../../sage/system_context.py) for the implementation.

## Implementation

| Function | Purpose | Location |
|----------|---------|----------|
| `get_system_folder()` | Get system folder path | [`system_context.py:44`](../../sage/system_context.py) |
| `load_system_files()` | Load files with priority | [`system_context.py:97`](../../sage/system_context.py) |
| `format_system_context()` | Format for injection | [`system_context.py:250`](../../sage/system_context.py) |
| `save_system_file()` | Save a system file | [`system_context.py:326`](../../sage/system_context.py) |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `system_folder_enabled` | `true` | Enable/disable system folder |
| `system_folder_max_tokens` | `2000` | Token budget for system context |

## Best Practices

1. **Keep it focused** — System files should be concise and actionable
2. **Use objective.md** — Always have a clear current goal
3. **Document constraints** — What should Claude avoid doing?
4. **Pin sparingly** — Only pin truly essential reference material
5. **Review regularly** — Update objectives as work progresses
