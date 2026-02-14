# Code Context Capture

Checkpoints automatically capture what code you explored during research, creating a traceable link between conclusions and evidence.

## Why This Matters

### For Agents
Subagents have separate context windows. When Agent B needs to understand what Agent A already explored, it can load a checkpoint with `files_explored` rather than re-reading the same files.

### For Learning Engineers
The most dangerous part of AI-assisted learning is **false progress** — feeling like you understand because you got something working, without actually grasping why.

Code context capture makes your exploration visible:
- "I looked at these 12 files"
- "I changed these 3 files"
- "These specific code sections informed my conclusion"

When you review a checkpoint later, you can trace *exactly* what evidence led to your understanding.

## How It Works

### Automatic Capture

When you save a checkpoint, Sage reads the Claude Code transcript (JSONL) and extracts file interactions:

```
┌─────────────────────────────────────────────────────────────┐
│  Claude Code Transcript (JSONL)                              │
├─────────────────────────────────────────────────────────────┤
│  {"tool": "Read", "input": {"file_path": "src/auth.py"}}    │
│  {"tool": "Edit", "input": {"file_path": "src/login.py"}}   │
│  {"tool": "Grep", "input": {"pattern": "authenticate"}}     │
│  ...                                                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  SessionCodeContext                                          │
├─────────────────────────────────────────────────────────────┤
│  files_read: {src/auth.py, src/user.py, tests/test_auth.py} │
│  files_edited: {src/login.py}                               │
│  files_written: {}                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Checkpoint                                                  │
├─────────────────────────────────────────────────────────────┤
│  thesis: "JWT tokens with refresh rotation..."              │
│  files_explored: {src/auth.py, src/user.py, ...}           │
│  files_changed: {src/login.py}                              │
│  code_refs: [{file: "src/auth.py", lines: (45, 67), ...}]  │
└─────────────────────────────────────────────────────────────┘
```

### Supported Tool Types

| Tool | Action | What's Captured |
|------|--------|-----------------|
| `Read` | read | File path, line range (if specified) |
| `Edit` | edit | File path |
| `Write` | write | File path |
| `Grep` | grep | Files that matched |
| `Glob` | glob | Files that matched |
| `NotebookEdit` | edit | Notebook path |

## Data Structures

### FileInteraction

Individual file operation from the transcript:

```python
@dataclass(frozen=True)
class FileInteraction:
    file: str                          # Absolute file path
    action: str                        # read | edit | write | grep | glob
    timestamp: str                     # ISO timestamp
    lines: tuple[int, int] | None      # For reads with offset/limit
```

**Source:** [`sage/transcript.py:18-31`](../../sage/transcript.py)

### SessionCodeContext

Aggregated context for a session:

```python
@dataclass(frozen=True)
class SessionCodeContext:
    interactions: tuple[FileInteraction, ...]
    files_read: frozenset[str]
    files_edited: frozenset[str]
    files_written: frozenset[str]

    @property
    def files_changed(self) -> frozenset[str]:
        return self.files_edited | self.files_written

    @property
    def all_files(self) -> frozenset[str]:
        return self.files_read | self.files_edited | self.files_written
```

**Source:** [`sage/transcript.py:34-58`](../../sage/transcript.py)

### CodeRef

Link to specific code that informed a checkpoint:

```python
@dataclass(frozen=True)
class CodeRef:
    file: str                           # Relative file path
    lines: tuple[int, int] | None       # Line range (optional)
    chunk_id: str | None                # Link to code index (for hydration)
    snippet: str | None                 # Cached code snippet
    relevance: str = "context"          # supports | contradicts | context | stale
```

**Source:** [`sage/checkpoint.py:52-67`](../../sage/checkpoint.py)

## Checkpoint Fields

| Field | Type | Description |
|-------|------|-------------|
| `files_explored` | `frozenset[str]` | Files read during the session |
| `files_changed` | `frozenset[str]` | Files edited or written |
| `code_refs` | `tuple[CodeRef, ...]` | Links to specific code locations |

## Usage

### Automatic (Default)

Code context is captured automatically when saving checkpoints:

```python
sage_save_checkpoint(
    core_question="How does authentication work?",
    thesis="JWT tokens with refresh rotation...",
    confidence=0.85
    # auto_code_context=True (default)
)

# Response:
# "📍 Checkpoint saved [12 files changed]: JWT tokens with..."
```

### Disable Auto-Capture

```python
sage_save_checkpoint(
    core_question="...",
    thesis="...",
    confidence=0.8,
    auto_code_context=False  # Skip transcript parsing
)
```

### Manual Code Refs

You can also provide explicit code references:

```python
sage_save_checkpoint(
    core_question="...",
    thesis="...",
    confidence=0.8,
    code_refs=[
        {"file": "src/auth.py", "lines": [45, 67], "relevance": "supports"},
        {"file": "src/user.py", "relevance": "context"}
    ]
)
```

## Learning-Oriented Usage

### As a Study Journal

After a research session, your checkpoint becomes a study log:

```markdown
# How does the payment processing pipeline work?

## Thesis
Payments flow through validation → processing → settlement with
idempotency keys preventing duplicates...

## Files Explored (12 files)
- src/payments/validator.py
- src/payments/processor.py
- src/payments/settlement.py
- tests/test_payments.py
...

## Files Changed (2 files)
- src/payments/processor.py (added logging)
- tests/test_payments.py (added edge case)

## Code References
- **src/payments/processor.py:45-67** (supports)
  The idempotency check happens before any state mutation...

## Reasoning Trace
Started by looking at the API endpoint. Followed the call chain
into processor.py. Got confused by the async settlement — had to
read settlement.py to understand the queue pattern. The key insight
was that idempotency is checked at the processor level, not the API.
```

### Reviewing Your Learning

When you come back to this checkpoint:

1. **What did you explore?** — `files_explored` shows your journey
2. **What did you change?** — `files_changed` shows where you experimented
3. **What was the key evidence?** — `code_refs` with `relevance: supports`
4. **How did you figure it out?** — `reasoning_trace` shows your thinking

This is the difference between "I know how payments work" and "I understand *why* I know how payments work."

## Implementation Details

### Transcript Parsing

```python
from sage.transcript import (
    extract_file_interactions,
    build_session_code_context,
    get_session_code_context,
)

# Parse a transcript file
context = get_session_code_context(Path("~/.claude/projects/.../transcript.jsonl"))

print(f"Read {len(context.files_read)} files")
print(f"Changed {len(context.files_changed)} files")
```

### Checkpoint Enrichment

```python
from sage.checkpoint import enrich_checkpoint_with_code_context

# Add code context to an existing checkpoint
enriched = enrich_checkpoint_with_code_context(checkpoint, transcript_path)
```

## Related

- [Checkpointing](./checkpointing.md) — Full checkpoint system
- [Code Indexing](./code-indexing.md) — Semantic search over code
- [Embeddings](./embeddings.md) — Code vs prose embedding models
