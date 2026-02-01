# Sage Code RAG Spec

## Overview

Extend Sage with codebase indexing and retrieval. Enable semantic search over code and auto-injection of core context at session start.

Based on proven patterns from `ethereum-mcp`.

## Goals

1. **Index codebases** - Chunk by AST (functions/classes), embed, store
2. **Semantic search** - RAG over indexed code for ad-hoc queries
3. **Core context** - Mark important files for auto-injection at session start

## New MCP Tools

### `sage_index_code(path, project?)`

Scan directory, chunk code by AST, embed, store in LanceDB.

```python
sage_index_code(path="src/", project="crucible")
# → Indexed 847 chunks from 42 files
```

**Behavior:**
- Walks directory, filters by language (`.py`, `.ts`, `.js`, `.sol`, etc.)
- Parses with tree-sitter to extract functions/classes as chunks
- Falls back to recursive character splitting for non-parseable files
- Embeds with `all-MiniLM-L6-v2` (same as knowledge)
- Stores in LanceDB with metadata

### `sage_search_code(query, project?, limit?)`

RAG search over indexed code.

```python
sage_search_code(query="how does enforcement work", project="crucible")
# → Returns top 5 relevant code chunks with file:line references
```

**Behavior:**
- Embeds query
- Cosine similarity search in LanceDB
- Returns chunks with metadata (file, function, class, line range)
- Optional project filter

### `sage_mark_core(path, summary?)`

Mark file as "core" for auto-injection at session start.

```python
sage_mark_core(path="src/crucible/server.py", summary="MCP server entry points")
sage_mark_core(path="src/crucible/enforcement/patterns.py", summary="Pattern matching engine")
```

**Behavior:**
- Stores in `~/.sage/codebase/core_files.yaml`
- Summary is optional but helps with context injection
- Core files are injected via `sage_continuity_status()` at session start

### `sage_list_core(project?)`

List marked core files.

### `sage_unmark_core(path)`

Remove core file marking.

## Storage

```
~/.sage/
├── codebase/
│   ├── lancedb/              # Vector store (per-project tables)
│   │   ├── crucible/
│   │   ├── sage/
│   │   └── ...
│   └── core_files.yaml       # Manually marked important files
```

### LanceDB Schema

```python
{
    "content": str,           # Chunk text (function/class body)
    "vector": list[float],    # Embedding (384-dim for MiniLM)
    "file": str,              # Relative file path
    "project": str,           # Project name
    "language": str,          # python, typescript, solidity, etc.
    "chunk_type": str,        # function, class, method, module
    "name": str,              # Function/class name
    "line_start": int,        # Start line number
    "line_end": int,          # End line number
    "docstring": str,         # Extracted docstring if present
}
```

### Core Files YAML

```yaml
crucible:
  - path: src/crucible/server.py
    summary: MCP server entry points and tool handlers
  - path: src/crucible/enforcement/patterns.py
    summary: Pattern matching engine for assertions

sage:
  - path: src/sage/checkpoints.py
    summary: Checkpoint save/load logic
```

## Chunking Strategy

### AST-Aware (Primary)

Use tree-sitter for language-aware parsing:

| Language | Chunk on |
|----------|----------|
| Python | `function_definition`, `class_definition` |
| TypeScript/JS | `function_declaration`, `class_declaration`, `arrow_function` |
| Solidity | `function_definition`, `contract_definition` |
| Go | `function_declaration`, `method_declaration` |
| Rust | `function_item`, `impl_item` |

Each chunk includes:
- Full function/class body
- Docstring/comments immediately preceding
- Name and signature for metadata

### Fallback (Character Splitting)

For files that fail AST parsing or unsupported languages:
- Chunk size: 1000 characters
- Overlap: 200 characters
- Split on line boundaries

## Session Start Integration

Extend `sage_continuity_status()`:

```python
def sage_continuity_status():
    # ... existing checkpoint continuity ...

    # NEW: Inject core file context
    core_files = load_core_files(project=current_project)
    if core_files:
        context += "\n\n## Core Codebase Context\n"
        for f in core_files:
            context += f"\n### {f.path}\n{f.summary}\n"
            # Optionally include key function signatures
```

## Implementation Notes

### Dependencies

```
lancedb>=0.4.0
sentence-transformers>=2.2.0
tree-sitter>=0.20.0
tree-sitter-python
tree-sitter-javascript
tree-sitter-typescript
# Add more tree-sitter grammars as needed
```

### Embedding Model

Reuse existing Sage embedding setup:
- Model: `all-MiniLM-L6-v2` (fast, CPU-friendly, 384-dim)
- Batch processing for indexing
- Single query encoding for search

### Incremental Indexing

Future enhancement:
- Track file mtimes
- Only re-index changed files
- Delete chunks for removed files

### Project Detection

Auto-detect project name from:
1. Explicit `project` parameter
2. Git remote name
3. Directory name

## Example Usage

```python
# Index a codebase
sage_index_code(path="/Users/me/crucible/src", project="crucible")

# Search for relevant code
sage_search_code(query="how do pattern assertions work")
# → Returns enforcement/patterns.py:run_pattern_assertions(), etc.

# Mark important files for session injection
sage_mark_core("src/crucible/server.py", "MCP entry points")
sage_mark_core("src/crucible/models.py", "Core data models")

# Next session: automatically get core context
sage_continuity_status()
# → Injects checkpoints + core file summaries
```

## Out of Scope (Future)

- Cross-project search
- Automatic "importance" detection (most imported, most changed)
- Call graph analysis
- Inline code comments as separate chunks
- Real-time file watching

## Migration Path

1. Add LanceDB + tree-sitter dependencies
2. Implement `sage_index_code` with AST chunking
3. Implement `sage_search_code` with basic RAG
4. Add `sage_mark_core` / `sage_list_core`
5. Integrate core files into `sage_continuity_status`
6. Add incremental indexing (optional optimization)
