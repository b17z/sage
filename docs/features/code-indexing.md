# Code Indexing

Sage indexes codebases for semantic search — find code by *intent*, not just keywords.

## Why This Matters

### For Agents
On large codebases, agents spend significant time re-reading files to build context. Code indexing lets them ask "where does authentication happen?" and get relevant code chunks instantly.

### For Learning Engineers
When exploring a new codebase, you often know *what* you're looking for conceptually but not *where* it is. Semantic search bridges that gap:

```
"how are errors handled" → finds try/except patterns, error middleware, etc.
"authentication flow"    → finds login, JWT, session code
"database transactions"  → finds commit/rollback patterns
```

This supports **directed exploration** — you're still reading and understanding the code, but you're finding the right code to read.

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Source Code                                                 │
│  *.py, *.ts, *.go, *.rs, *.sol, ...                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  AST-Aware Chunking                                          │
│  Split by: functions, classes, methods, constants            │
│  Preserve: signatures, docstrings, context                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  CodeSage Embeddings                                         │
│  Model: codesage/codesage-large (1024 dim)                  │
│  Optimized for programming constructs                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────┬──────────────────────────────────┐
│  LanceDB (Vector)        │  Compiled Index (JSON)           │
│  Semantic search         │  Fast exact lookup               │
│  ~/.sage/codebase/lancedb│  <project>/.sage/codebase/compiled│
└──────────────────────────┴──────────────────────────────────┘
```

### Chunking Strategy

Code is split into semantic units, not arbitrary character blocks:

| Chunk Type | Description | Example |
|------------|-------------|---------|
| `function` | Function definitions | `def authenticate(user):` |
| `class` | Class definitions | `class UserService:` |
| `method` | Class methods | `def validate(self):` |
| `module` | Top-level imports/docstrings | Module docstring |
| `constant` | Module-level constants | `MAX_RETRIES = 3` |
| `type` | Type aliases, interfaces | `type UserId = str` |
| `fallback` | Character-based for unsupported languages | Generic chunking |

**Source:** [`sage/codebase/chunker.py`](../../sage/codebase/chunker.py)

### Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Solidity, Ruby, Java, Kotlin, C, C++, C#, Swift, Objective-C, Scala, Lua, R, Julia, Haskell, Elixir, Erlang, Clojure, OCaml, PHP, Bash, SQL, GraphQL, Protocol Buffers, YAML, TOML, JSON, Markdown, Vue, Svelte.

**Source:** [`sage/codebase/models.py:170-222`](../../sage/codebase/models.py)

## Usage

### CLI Commands

```bash
# Index current directory
sage index

# Index specific project
sage index /path/to/project

# Incremental (only changed files) - default
sage index --incremental

# Full re-index
sage index --full

# Search code
sage search "authentication flow"

# Fast exact lookup
sage grep authenticate_user

# Get full function source
sage analyze authenticate_user
```

### MCP Tools

```python
# Index a directory
result = sage_index_code(
    path=".",
    project="my-project",      # Auto-detected if not specified
    incremental=True           # Only changed files (default)
)

# Returns:
# IndexStats(
#     project="my-project",
#     files_indexed=42,
#     chunks_created=312,
#     functions_compiled=89,
#     classes_compiled=23,
#     constants_compiled=15,
#     languages=("python", "typescript"),
#     duration_ms=1234
# )
```

### Semantic Search

```python
# Find code by intent
results = sage_search_code(
    query="how does authentication work",
    project="my-project",       # Optional filter
    limit=10,
    language="python"           # Optional filter
)

# Returns list of SearchResult:
# - chunk: CodeChunk with content, location, metadata
# - score: similarity (0-1)
# - highlights: matching snippets
```

### Fast Symbol Lookup

For exact symbol names, skip vector search:

```python
# Exact lookup (no embedding search)
result = sage_grep_symbol("authenticate_user")
# Returns CompiledFunction | CompiledClass | CompiledConstant | None

# Get full function source
source = sage_analyze_function("authenticate_user", project_path)
# Returns dict with name, signature, file, line, docstring, source
```

## Data Structures

### CodeChunk

A semantic unit of code:

```python
@dataclass(frozen=True)
class CodeChunk:
    id: str                    # Unique ID: "{file_hash}:{line}:{name}"
    file: str                  # Relative path from project root
    project: str               # Project identifier
    content: str               # The actual code content
    chunk_type: ChunkType      # function, class, method, etc.
    name: str                  # Symbol name
    line_start: int
    line_end: int
    language: str              # Programming language
    docstring: str = ""        # Extracted docstring
    signature: str = ""        # Function/method signature
    parent: str = ""           # Parent class/module name
    embedding: list[float]     # Vector (set after embedding)
```

**Source:** [`sage/codebase/models.py:24-54`](../../sage/codebase/models.py)

### CompiledFunction

Fast-lookup metadata (no vectors):

```python
@dataclass(frozen=True)
class CompiledFunction:
    name: str
    signature: str
    file: str                  # Relative path
    line: int
    docstring: str = ""
    is_method: bool = False
    parent_class: str = ""
```

**Source:** [`sage/codebase/models.py:57-70`](../../sage/codebase/models.py)

### SearchResult

```python
@dataclass(frozen=True)
class SearchResult:
    chunk: CodeChunk
    score: float               # Similarity (0-1)
    highlights: tuple[str, ...]  # Matching snippets
```

**Source:** [`sage/codebase/models.py:161-167`](../../sage/codebase/models.py)

## Learning-Oriented Usage

### Guided Exploration

Instead of asking Claude "how does auth work?" and getting a summary, use code search for **directed exploration**:

```python
# You: "I want to understand authentication"
results = sage_search_code("authentication user login")

# Returns:
# 1. src/auth/jwt.py:45 - JWTHandler.create_token()
# 2. src/auth/middleware.py:23 - authenticate_request()
# 3. src/users/login.py:67 - LoginService.login()
```

Now you have a **reading list** — specific files and functions to study. You're doing the learning, but AI helped you find the right starting points.

### Building Mental Models

After exploring code, checkpoint your understanding:

```python
sage_save_checkpoint(
    core_question="How does authentication work in this codebase?",
    thesis="JWT-based auth with middleware validation...",
    confidence=0.8,
    code_refs=[
        {"file": "src/auth/jwt.py", "lines": [45, 89], "relevance": "supports"},
        {"file": "src/auth/middleware.py", "lines": [23, 56], "relevance": "supports"}
    ],
    reasoning_trace="""
    Started with sage_search_code("authentication").
    Found JWT handler in auth/jwt.py - this creates tokens.
    Followed to middleware.py - this validates on each request.
    Key insight: tokens are stateless, validation happens per-request.
    """
)
```

Your checkpoint now links understanding to specific code evidence.

### The Anti-Pattern

What *not* to do:

```
You: "How does auth work?"
AI: "Auth uses JWT tokens. Here's how to add a new endpoint..."
You: "Cool, it works!"
```

You got something working, but did you understand jwt.py? middleware.py? Where tokens are validated? What happens on expiry?

The code index supports a better pattern:
```
You: "Where is auth code?"
AI: [gives you a reading list]
You: [reads the code, builds understanding]
You: "I don't get the middleware part"
AI: [explains that specific part]
You: [checkpoints your understanding with code refs]
```

## Storage Layout

```
~/.sage/
└── codebase/
    └── lancedb/              # Global vector database

<project>/.sage/
└── codebase/
    ├── compiled/             # Fast JSON lookup
    │   ├── functions.json
    │   ├── classes.json
    │   └── constants.json
    └── index_meta.json       # Index state (mtimes, project)
```

## Configuration

```yaml
# ~/.sage/tuning.yaml

# Code embedding model
code_embedding_model: codesage/codesage-large  # Default
# or
code_embedding_model: codesage/codesage-small  # Lighter
```

## Implementation

### Key Files

| File | Purpose |
|------|---------|
| `sage/codebase/indexer.py` | Indexing orchestration |
| `sage/codebase/chunker.py` | AST-aware code splitting |
| `sage/codebase/compiler.py` | Compiled index generation |
| `sage/codebase/search.py` | Semantic and exact search |
| `sage/codebase/models.py` | Data structures |

### Incremental Indexing

Index tracks file mtimes to only re-index changed files:

```python
meta = {
    "files": {
        "src/auth.py": 1707849600.0,   # mtime
        "src/users.py": 1707849500.0,
    },
    "indexed_at": "2026-02-13T12:00:00Z",
    "project": "my-project"
}
```

On re-index, only files with newer mtime are processed.

## Related

- [Embeddings](./embeddings.md) — Code vs prose embedding models
- [Code Context Capture](./code-context.md) — Track explored files
- [Checkpointing](./checkpointing.md) — Save research with code refs
