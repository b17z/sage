"""Embedding model wrapper for semantic similarity.

This module provides:
- Lazy-loaded embedding model (sentence-transformers)
- Embedding generation and storage
- Cosine similarity computation
- Similar item retrieval

All embedding features are optional and fall back gracefully
when the sentence-transformers package is not installed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from sage.config import SAGE_DIR
from sage.errors import Result, SageError, err, ok

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Default model - good balance of size (~80MB) and quality
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# Directory for embedding storage
EMBEDDINGS_DIR = SAGE_DIR / "embeddings"

# Similarity thresholds
RECALL_THRESHOLD = 0.7  # For knowledge recall
DEDUP_THRESHOLD = 0.9  # For checkpoint deduplication


@dataclass(frozen=True)
class EmbeddingConfig:
    """Configuration for embedding operations."""

    model_name: str = DEFAULT_MODEL
    recall_threshold: float = RECALL_THRESHOLD
    dedup_threshold: float = DEDUP_THRESHOLD


# Global model instance (lazy-loaded)
_model: SentenceTransformer | None = None
_model_name: str | None = None


def is_available() -> bool:
    """Check if sentence-transformers is available."""
    try:
        import sentence_transformers  # noqa: F401

        return True
    except ImportError:
        return False


def get_model(model_name: str = DEFAULT_MODEL) -> Result[SentenceTransformer, SageError]:
    """Get or load the embedding model (lazy initialization).

    Args:
        model_name: HuggingFace model identifier

    Returns:
        Result containing the model or an error
    """
    global _model, _model_name

    if not is_available():
        return err(
            SageError(
                code="embeddings_unavailable",
                message="sentence-transformers not installed. Install with: pip install sage-research[embeddings]",
                context={},
            )
        )

    # Return cached model if same name
    if _model is not None and _model_name == model_name:
        return ok(_model)

    try:
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading embedding model: {model_name}")
        _model = SentenceTransformer(model_name)
        _model_name = model_name
        logger.info(f"Model loaded successfully (dim={_model.get_sentence_embedding_dimension()})")
        return ok(_model)

    except Exception as e:
        return err(
            SageError(
                code="model_load_failed",
                message=f"Failed to load embedding model: {e}",
                context={"model_name": model_name},
            )
        )


def get_embedding(text: str, model_name: str = DEFAULT_MODEL) -> Result[np.ndarray, SageError]:
    """Generate embedding for a single text.

    Args:
        text: Text to embed
        model_name: Model to use

    Returns:
        Result containing the embedding vector or an error
    """
    model_result = get_model(model_name)
    if model_result.is_err():
        return err(model_result.unwrap_err())

    model = model_result.unwrap()
    try:
        embedding = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return ok(embedding)
    except Exception as e:
        return err(
            SageError(
                code="embedding_failed",
                message=f"Failed to generate embedding: {e}",
                context={"text_length": len(text)},
            )
        )


def get_embeddings_batch(
    texts: list[str], model_name: str = DEFAULT_MODEL
) -> Result[np.ndarray, SageError]:
    """Generate embeddings for multiple texts (batched for efficiency).

    Args:
        texts: List of texts to embed
        model_name: Model to use

    Returns:
        Result containing array of embeddings (shape: [n_texts, dim]) or an error
    """
    if not texts:
        return ok(np.array([]))

    model_result = get_model(model_name)
    if model_result.is_err():
        return err(model_result.unwrap_err())

    model = model_result.unwrap()
    try:
        embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return ok(embeddings)
    except Exception as e:
        return err(
            SageError(
                code="embedding_failed",
                message=f"Failed to generate batch embeddings: {e}",
                context={"batch_size": len(texts)},
            )
        )


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors.

    Note: If vectors are already normalized (which they are from encode),
    this is equivalent to dot product.

    Args:
        a: First embedding vector
        b: Second embedding vector

    Returns:
        Cosine similarity score (-1 to 1, typically 0 to 1 for text)
    """
    # Handle edge cases
    if a.size == 0 or b.size == 0:
        return 0.0

    # For normalized vectors, cosine similarity = dot product
    return float(np.dot(a, b))


def cosine_similarity_matrix(query: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
    """Compute cosine similarities between query and multiple embeddings.

    Args:
        query: Single query embedding (1D array)
        embeddings: Matrix of embeddings (2D array, shape: [n, dim])

    Returns:
        Array of similarity scores (shape: [n])
    """
    if query.size == 0 or embeddings.size == 0:
        return np.array([])

    # For normalized vectors: similarities = embeddings @ query
    return embeddings @ query


@dataclass(frozen=True)
class EmbeddingStore:
    """Storage for embeddings with string IDs."""

    ids: list[str]
    embeddings: np.ndarray  # Shape: [n_items, embedding_dim]

    @classmethod
    def empty(cls, dim: int = 384) -> EmbeddingStore:
        """Create an empty store."""
        return cls(ids=[], embeddings=np.empty((0, dim)))

    def __len__(self) -> int:
        return len(self.ids)

    def get(self, item_id: str) -> np.ndarray | None:
        """Get embedding by ID."""
        try:
            idx = self.ids.index(item_id)
            return self.embeddings[idx]
        except ValueError:
            return None

    def add(self, item_id: str, embedding: np.ndarray) -> EmbeddingStore:
        """Add or update an embedding. Returns new store (immutable)."""
        new_ids = list(self.ids)
        new_embeddings = (
            self.embeddings.copy() if self.embeddings.size > 0 else np.empty((0, len(embedding)))
        )

        try:
            # Update existing
            idx = new_ids.index(item_id)
            new_embeddings[idx] = embedding
        except ValueError:
            # Add new
            new_ids.append(item_id)
            new_embeddings = (
                np.vstack([new_embeddings, embedding[np.newaxis, :]])
                if new_embeddings.size > 0
                else embedding[np.newaxis, :]
            )

        return EmbeddingStore(ids=new_ids, embeddings=new_embeddings)

    def remove(self, item_id: str) -> EmbeddingStore:
        """Remove an embedding by ID. Returns new store (immutable)."""
        try:
            idx = self.ids.index(item_id)
            new_ids = [id_ for i, id_ in enumerate(self.ids) if i != idx]
            new_embeddings = np.delete(self.embeddings, idx, axis=0)
            return EmbeddingStore(ids=new_ids, embeddings=new_embeddings)
        except ValueError:
            return self  # ID not found, return unchanged


def load_embeddings(path: Path) -> Result[EmbeddingStore, SageError]:
    """Load embeddings from disk.

    Embeddings are stored as .npy (no pickle) with IDs in a separate .json file
    for security (avoids arbitrary code execution from malicious pickle data).

    Args:
        path: Path to .npy embeddings file

    Returns:
        Result containing EmbeddingStore or an error
    """
    ids_path = path.with_suffix(".json")
    
    if not path.exists():
        return ok(EmbeddingStore.empty())

    try:
        # Load embeddings without pickle (security)
        embeddings = np.load(path, allow_pickle=False)
        
        # Load IDs from JSON
        if ids_path.exists():
            with open(ids_path) as f:
                ids = json.load(f)
        else:
            ids = []
        
        return ok(EmbeddingStore(ids=ids, embeddings=embeddings))
    except Exception as e:
        return err(
            SageError(
                code="load_embeddings_failed",
                message=f"Failed to load embeddings: {e}",
                context={"path": str(path)},
            )
        )


def save_embeddings(path: Path, store: EmbeddingStore) -> Result[None, SageError]:
    """Save embeddings to disk.

    Embeddings are stored as .npy (no pickle) with IDs in a separate .json file
    for security (avoids arbitrary code execution from malicious pickle data).

    Args:
        path: Path to .npy embeddings file
        store: EmbeddingStore to save

    Returns:
        Result with None on success or an error
    """
    ids_path = path.with_suffix(".json")
    
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save embeddings without pickle (security)
        np.save(path, store.embeddings)
        # Restrict permissions - embeddings may reveal model behavior
        path.chmod(0o600)

        # Save IDs as JSON (safe, no code execution)
        with open(ids_path, "w") as f:
            json.dump(store.ids, f)
        ids_path.chmod(0o600)

        return ok(None)
    except Exception as e:
        return err(
            SageError(
                code="save_embeddings_failed",
                message=f"Failed to save embeddings: {e}",
                context={"path": str(path)},
            )
        )


@dataclass(frozen=True)
class SimilarItem:
    """Result of similarity search."""

    id: str
    score: float


def find_similar(
    query_embedding: np.ndarray,
    store: EmbeddingStore,
    threshold: float = 0.0,
    top_k: int | None = None,
) -> list[SimilarItem]:
    """Find items similar to query embedding.

    Args:
        query_embedding: Query embedding vector
        store: EmbeddingStore to search
        threshold: Minimum similarity threshold
        top_k: Maximum number of results (None for all above threshold)

    Returns:
        List of SimilarItem sorted by score (highest first)
    """
    if len(store) == 0:
        return []

    # Compute similarities
    similarities = cosine_similarity_matrix(query_embedding, store.embeddings)

    # Filter and sort
    results = []
    for idx, score in enumerate(similarities):
        if score >= threshold:
            results.append(SimilarItem(id=store.ids[idx], score=float(score)))

    # Sort by score descending
    results.sort(key=lambda x: x.score, reverse=True)

    # Limit results
    if top_k is not None:
        results = results[:top_k]

    return results


def get_knowledge_embeddings_path() -> Path:
    """Get path to knowledge embeddings file."""
    return EMBEDDINGS_DIR / "knowledge.npy"


def get_checkpoint_embeddings_path() -> Path:
    """Get path to checkpoint embeddings file."""
    return EMBEDDINGS_DIR / "checkpoints.npy"


def ensure_embeddings_dir() -> None:
    """Create embeddings directory if it doesn't exist."""
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
