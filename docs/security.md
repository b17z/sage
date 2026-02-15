# Security

Sage handles user research data, code context, and file paths. This document covers security measures implemented across the codebase.

## Threat Model

| Threat | Mitigation | Location |
|--------|------------|----------|
| Path traversal | Path validation, containment checks | `mcp_server.py`, `failures.py` |
| Command injection | No shell execution of user input | Throughout |
| Data exposure | Restricted file permissions (0o600) | `atomic.py`, `system_context.py` |
| Insecure deserialization | YAML safe_load only | `checkpoint.py`, `knowledge.py`, `failures.py` |
| Unauthorized access | Resource validation | `mcp_server.py` |

## Path Validation

### MCP Resources (v4.0)

All MCP resources validate paths before access:

```python
# sage/mcp_server.py:2821
def _validate_sage_path(path: str) -> str | None:
    """Validate that a path is safe for Sage resources."""
    # Block path traversal
    if ".." in path or path.startswith("/") or path.startswith("\\"):
        return None

    # Allow only safe characters
    if not re.match(r"^[a-zA-Z0-9_\-./]+$", path):
        return None

    # Remove leading/trailing slashes
    return path.strip("/")
```

**What's blocked:**
- `../etc/passwd` — Path traversal
- `/etc/passwd` — Absolute paths
- `test;rm -rf /` — Shell metacharacters
- `test|cat /etc` — Pipe injection
- `test$(whoami)` — Command substitution

### System File Resources

Additional containment check for system files:

```python
# sage/mcp_server.py:2872
file_path = file_path.resolve()
if system_folder.resolve() not in file_path.parents:
    return "File not in system folder"
```

This prevents symlink attacks and ensures files are within `.sage/system/`.

### Failure ID Sanitization

Failure IDs are sanitized before use in filenames:

```python
# sage/failures.py:96
def _sanitize_id(raw_id: str) -> str:
    """Sanitize an ID to prevent path traversal attacks."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_id).strip("-")
    return sanitized or "unnamed"
```

**Input → Output:**
- `../../../etc/passwd` → `etc-passwd`
- `normal-id` → `normal-id`
- `test@failure!` → `test-failure`

## Safe Deserialization

Sage uses YAML for configuration and storage. All YAML parsing uses `safe_load`:

```python
# Correct (used throughout)
data = yaml.safe_load(content)

# Dangerous (NEVER used)
data = yaml.load(content, Loader=yaml.Loader)
```

**Files using safe_load:**
- `sage/checkpoint.py` — Checkpoint frontmatter
- `sage/knowledge.py` — Knowledge frontmatter
- `sage/failures.py` — Failure frontmatter
- `sage/config.py` — Configuration files
- `sage/system_context.py` — System context parsing

### Why This Matters

`yaml.load()` with default loader can execute arbitrary Python code:

```yaml
# Malicious YAML that would execute code
!!python/object/apply:os.system ["rm -rf /"]
```

`yaml.safe_load()` only allows basic types (strings, numbers, lists, dicts).

## File Permissions

Sensitive files are created with restricted permissions:

```python
# sage/atomic.py
def atomic_write_text(path: Path, content: str, mode: int = 0o600) -> Result:
    """Write content atomically with restricted permissions."""
    ...
    os.chmod(tmp.name, mode)
```

**Default: 0o600** — Owner read/write only.

Used for:
- Checkpoints
- Knowledge items
- Failures
- System folder files

## Error Message Safety

Error messages don't expose internal paths or sensitive data:

```python
# Good - no internal details
return f"Invalid filename: {filename}"
return f"Checkpoint not found: {checkpoint_id}"

# Bad - would expose paths
return f"File not found at {full_internal_path}"
```

## Input Validation

All MCP tool inputs are validated:

```python
@mcp.tool()
def sage_record_failure(
    failure_id: str,      # Sanitized via _sanitize_id
    approach: str,        # Stored as-is (no execution)
    why_failed: str,      # Stored as-is
    learned: str,         # Stored as-is
    keywords: list[str],  # Stored as-is
    ...
) -> str:
```

User-provided text is stored in Markdown files but never:
- Executed as code
- Used in shell commands
- Used in SQL queries
- Rendered without escaping (UI handles this)

## Git Operations

Git versioning (v4.0) runs git commands safely:

```python
# sage/git.py
subprocess.run(
    ["git", "add", str(file_path)],  # No shell=True
    cwd=repo_path,
    capture_output=True,
    check=False,
)
```

**Safety measures:**
- `shell=False` (implicit) — No shell interpretation
- Arguments as list — No injection via string concatenation
- Paths validated before use

## Network Operations

Sage's network access is limited:

| Operation | URL | Purpose |
|-----------|-----|---------|
| PyPI check | `https://pypi.org/pypi/claude-sage/json` | Version updates |
| Embeddings | Configured model endpoint | Semantic search |

**PyPI check security:**
```python
# sage/__init__.py:81
if not _PYPI_URL.startswith("https://"):
    return False, None  # Only allow HTTPS
```

## Configuration Security

Sensitive config (API keys) goes in user-level config only:

```
~/.sage/config.yaml       # API keys - NEVER committed
<project>/.sage/          # Project config - safe to commit
```

Project-level `.sage/` is designed to be committed to git.

## Testing

Security-related tests:

| Test File | Coverage |
|-----------|----------|
| `tests/test_mcp_resources.py` | Path validation, traversal blocking |
| `tests/test_failures.py` | ID sanitization |
| `tests/test_system_context.py` | File containment |

Example security test:

```python
def test_blocks_path_traversal(self):
    """Should block path traversal attempts."""
    assert _validate_sage_path("../etc/passwd") is None
    assert _validate_sage_path("test/../../../etc") is None
    assert _validate_sage_path("..") is None

def test_blocks_special_characters(self):
    """Should block paths with special characters."""
    assert _validate_sage_path("test;rm -rf /") is None
    assert _validate_sage_path("test|cat /etc") is None
    assert _validate_sage_path("test$(whoami)") is None
```

## Security Checklist

For contributors adding new features:

- [ ] User input validated at entry point
- [ ] Paths validated with `_validate_sage_path()` or `_sanitize_id()`
- [ ] YAML parsed with `safe_load()` only
- [ ] Files created with 0o600 permissions via `atomic_write_text()`
- [ ] No `shell=True` in subprocess calls
- [ ] Error messages don't expose internal paths
- [ ] Tests cover malicious input cases

## Reporting Security Issues

If you discover a security vulnerability, please report it privately rather than opening a public issue. Contact the maintainers directly.
