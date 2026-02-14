# Embeddings

Sage uses embedding models to enable semantic search and similarity matching. It maintains **two separate embedding spaces** optimized for different content types.

## Dual Embedding Spaces

```
┌─────────────────────────────────────────┐
│               Sage Embeddings           │
├─────────────────┬───────────────────────┤
│  Prose (BGE)    │     Code (CodeSage)   │
├─────────────────┼───────────────────────┤
│ • Knowledge     │ • Code indexing       │
│ • Checkpoints   │ • Code search         │
│ • Query prefix  │ • No prefix needed    │
│ • Natural text  │ • Programming         │
└─────────────────┴───────────────────────┘
```

### Why Two Models?

Embedding models are trained on specific content types. A model trained on natural language text understands "authentication" as a concept. A model trained on code understands `def authenticate(user, password):` as a function signature with parameters.

Using the wrong model gives worse results:
- BGE on code: treats `def foo():` as weird English
- CodeSage on prose: treats "the authentication flow" as incomplete code

## Prose Model (BGE)

**Model:** `BAAI/bge-large-en-v1.5`

| Property | Value |
|----------|-------|
| Dimensions | 1024 |
| Size | ~1.3GB |
| MTEB Score | 63.0 |
| Query prefix | Required |

### Used For
- Knowledge items (storing and recall)
- Checkpoint thesis (deduplication, search)
- Natural language queries against knowledge

### Query Prefix

BGE models perform better when queries have a special prefix:

```python
# Document embedding (no prefix)
embedding = get_embedding("JWT tokens provide stateless auth")

# Query embedding (with prefix)
embedding = get_query_embedding("how does authentication work")
# Internally adds: "Represent this sentence for searching relevant passages: "
```

Sage handles this automatically — use `get_embedding()` for documents, `get_query_embedding()` for searches.

**Source:** [`sage/embeddings.py:318-339`](../../sage/embeddings.py)

## Code Model (CodeSage)

**Model:** `codesage/codesage-large`

| Property | Value |
|----------|-------|
| Dimensions | 1024 |
| Size | ~1.3GB |
| Max tokens | 1024 |
| Query prefix | Not needed |

### Used For
- Code chunk indexing
- Semantic code search
- Code similarity matching

### Why CodeSage?

CodeSage is trained on code from GitHub. It understands:
- Function signatures and parameters
- Class hierarchies
- Variable naming conventions
- Code patterns and idioms

```python
# Code embedding
embedding = get_code_embedding("def authenticate(user, password):")

# Code search query
embedding = get_code_query_embedding("authentication function")
```

**Source:** [`sage/embeddings.py:342-390`](../../sage/embeddings.py)

## API Reference

### Prose Functions

```python
from sage.embeddings import (
    get_embedding,           # Document embedding (no prefix)
    get_query_embedding,     # Query embedding (with BGE prefix)
    get_embeddings_batch,    # Batch document embeddings
)
```

### Code Functions

```python
from sage.embeddings import (
    get_code_embedding,           # Code content embedding
    get_code_query_embedding,     # Code search query
    get_code_embeddings_batch,    # Batch code embeddings
)
```

### Configuration

```python
from sage.embeddings import (
    get_configured_model,         # Returns prose model name
    get_configured_code_model,    # Returns code model name
    get_model_info,               # Model dimensions, prefix, size
)
```

## Configuration

### Tuning File

```yaml
# ~/.sage/tuning.yaml

# Prose model (knowledge, checkpoints)
embedding_model: BAAI/bge-large-en-v1.5   # Default

# Code model (code indexing, code search)
code_embedding_model: codesage/codesage-large   # Default
```

### Available Models

#### Prose Models

| Model | Dimensions | Size | Notes |
|-------|------------|------|-------|
| `BAAI/bge-large-en-v1.5` | 1024 | 1.3GB | Best quality (default) |
| `BAAI/bge-base-en-v1.5` | 768 | 440MB | Good balance |
| `BAAI/bge-small-en-v1.5` | 384 | 130MB | Fastest |
| `all-MiniLM-L6-v2` | 384 | 80MB | Lightweight fallback |

#### Code Models

| Model | Dimensions | Size | Notes |
|-------|------------|------|-------|
| `codesage/codesage-large` | 1024 | 1.3GB | Best quality (default) |
| `codesage/codesage-small` | 1024 | 435MB | Lighter alternative |

### Changing Models

After changing `embedding_model` or `code_embedding_model`:

```bash
# Rebuild embeddings to use new model
sage admin rebuild-embeddings
```

## Model Mismatch Detection

Sage tracks which model created existing embeddings. When you change models:

1. On load, Sage checks metadata for model mismatch
2. If mismatched, returns empty store (triggers rebuild)
3. Logs warning: "Embedding model changed... Embeddings will be rebuilt."

This prevents searching with one model against embeddings from another.

**Source:** [`sage/embeddings.py:484-499`](../../sage/embeddings.py)

## First Load Warning

On first use, Sage downloads the embedding model:

```
⚠️  Downloading embedding model (1340MB)... this only happens once.
```

Models are cached in the HuggingFace cache directory.

## Storage

### Embedding Files

```
~/.sage/embeddings/
├── knowledge.npy         # Knowledge embeddings
├── knowledge.json        # Knowledge IDs
├── checkpoints.npy       # Checkpoint embeddings
├── checkpoints.json      # Checkpoint IDs
└── meta.json             # Model metadata
```

### Security

- Embeddings use `np.save()` with `allow_pickle=False`
- No arbitrary code execution from embedding files
- File permissions set to 0o600

**Source:** [`sage/embeddings.py:502-584`](../../sage/embeddings.py)

## Learning Perspective

### Understanding Similarity

Embeddings convert text to vectors where similar meanings are close together:

```
"authentication" → [0.23, 0.45, ..., 0.12]  # 1024 numbers
"login system"   → [0.25, 0.44, ..., 0.11]  # Similar vector!
"database query" → [0.87, 0.12, ..., 0.56]  # Different vector
```

Cosine similarity measures how aligned two vectors are:
- 1.0 = identical meaning
- 0.0 = unrelated
- -1.0 = opposite

### Why This Matters for Learning

Traditional keyword search:
```
Search: "auth"
Results: Files containing "auth" substring
```

Semantic search:
```
Search: "how do users log in"
Results: Files about authentication, sessions, JWT, etc.
```

Semantic search finds conceptually relevant code even when exact words don't match. This helps you **find what to study** without knowing the exact terminology the codebase uses.

## Implementation Details

### EmbeddingStore

Immutable store for IDs + embeddings:

```python
@dataclass(frozen=True)
class EmbeddingStore:
    ids: list[str]
    embeddings: np.ndarray  # Shape: [n_items, dim]

    def get(self, item_id: str) -> np.ndarray | None: ...
    def add(self, item_id: str, embedding: np.ndarray) -> EmbeddingStore: ...
    def remove(self, item_id: str) -> EmbeddingStore: ...
```

**Source:** [`sage/embeddings.py:394-458`](../../sage/embeddings.py)

### Thread Safety

- Model loading uses threading lock (prevents concurrent initialization)
- File operations use fcntl locking (prevents corruption)
- Store is immutable (add/remove return new instance)

### Similarity Search

```python
from sage.embeddings import find_similar, SimilarItem

results: list[SimilarItem] = find_similar(
    query_embedding,
    store,
    threshold=0.7,    # Minimum similarity
    top_k=10          # Max results
)
```

**Source:** [`sage/embeddings.py:683-719`](../../sage/embeddings.py)

## Related

- [Code Indexing](./code-indexing.md) — Uses code embeddings
- [Knowledge System](./knowledge.md) — Uses prose embeddings
- [Checkpointing](./checkpointing.md) — Uses prose embeddings for dedup
