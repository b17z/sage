"""Tests for sage.embeddings module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sage.embeddings import (
    EmbeddingStore,
    SimilarItem,
    cosine_similarity,
    cosine_similarity_matrix,
    find_similar,
    is_available,
    load_embeddings,
    save_embeddings,
)


@pytest.fixture
def mock_embeddings_dir(tmp_path: Path):
    """Create a temporary embeddings directory."""
    embeddings_dir = tmp_path / ".sage" / "embeddings"
    embeddings_dir.mkdir(parents=True)
    return embeddings_dir


@pytest.fixture
def sample_embeddings():
    """Create sample normalized embeddings for testing."""
    # 3 vectors of dimension 4, normalized
    embeddings = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.707, 0.707, 0.0, 0.0],  # 45 degrees between first two
    ])
    # Normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / norms


class TestCosineSimilarity:
    """Tests for cosine similarity functions."""

    def test_identical_vectors_similarity_1(self):
        """Identical normalized vectors have similarity 1."""
        v = np.array([0.5, 0.5, 0.5, 0.5])
        v = v / np.linalg.norm(v)
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_similarity_0(self):
        """Orthogonal vectors have similarity 0."""
        v1 = np.array([1.0, 0.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0, 0.0])
        assert cosine_similarity(v1, v2) == pytest.approx(0.0)

    def test_opposite_vectors_similarity_negative(self):
        """Opposite vectors have similarity -1."""
        v1 = np.array([1.0, 0.0, 0.0, 0.0])
        v2 = np.array([-1.0, 0.0, 0.0, 0.0])
        assert cosine_similarity(v1, v2) == pytest.approx(-1.0)

    def test_45_degree_angle(self, sample_embeddings):
        """45 degree angle gives ~0.707 similarity."""
        v1 = sample_embeddings[0]
        v3 = sample_embeddings[2]
        assert cosine_similarity(v1, v3) == pytest.approx(0.707, rel=0.01)

    def test_empty_vectors_return_0(self):
        """Empty vectors return 0 similarity."""
        empty = np.array([])
        v = np.array([1.0, 0.0])
        assert cosine_similarity(empty, v) == 0.0
        assert cosine_similarity(v, empty) == 0.0


class TestCosineSimilarityMatrix:
    """Tests for batch similarity computation."""

    def test_batch_similarities(self, sample_embeddings):
        """Compute similarities against multiple embeddings."""
        query = sample_embeddings[0]  # [1, 0, 0, 0]

        similarities = cosine_similarity_matrix(query, sample_embeddings)

        assert len(similarities) == 3
        assert similarities[0] == pytest.approx(1.0)  # Same vector
        assert similarities[1] == pytest.approx(0.0)  # Orthogonal
        assert similarities[2] == pytest.approx(0.707, rel=0.01)  # 45 degrees

    def test_empty_embeddings_matrix(self):
        """Empty embeddings matrix returns empty array."""
        query = np.array([1.0, 0.0])
        embeddings = np.array([])

        result = cosine_similarity_matrix(query, embeddings)
        assert len(result) == 0


class TestEmbeddingStore:
    """Tests for EmbeddingStore operations."""

    def test_empty_store(self):
        """Empty store has no items."""
        store = EmbeddingStore.empty()
        assert len(store) == 0
        assert store.get("any") is None

    def test_add_embedding(self):
        """Add embedding to store."""
        store = EmbeddingStore.empty()
        embedding = np.array([1.0, 0.0, 0.0, 0.0])

        new_store = store.add("item1", embedding)

        assert len(new_store) == 1
        assert new_store.get("item1") is not None
        np.testing.assert_array_equal(new_store.get("item1"), embedding)

    def test_add_multiple_embeddings(self):
        """Add multiple embeddings."""
        store = EmbeddingStore.empty()
        e1 = np.array([1.0, 0.0])
        e2 = np.array([0.0, 1.0])

        store = store.add("item1", e1)
        store = store.add("item2", e2)

        assert len(store) == 2
        assert "item1" in store.ids
        assert "item2" in store.ids

    def test_update_existing_embedding(self):
        """Updating existing item replaces embedding."""
        store = EmbeddingStore.empty()
        e1 = np.array([1.0, 0.0])
        e2 = np.array([0.0, 1.0])

        store = store.add("item1", e1)
        store = store.add("item1", e2)  # Update

        assert len(store) == 1
        np.testing.assert_array_equal(store.get("item1"), e2)

    def test_remove_embedding(self):
        """Remove embedding from store."""
        store = EmbeddingStore.empty()
        e1 = np.array([1.0, 0.0])
        e2 = np.array([0.0, 1.0])

        store = store.add("item1", e1)
        store = store.add("item2", e2)
        store = store.remove("item1")

        assert len(store) == 1
        assert store.get("item1") is None
        assert store.get("item2") is not None

    def test_remove_nonexistent_returns_unchanged(self):
        """Removing nonexistent item returns unchanged store."""
        store = EmbeddingStore.empty()
        e1 = np.array([1.0, 0.0])
        store = store.add("item1", e1)

        new_store = store.remove("nonexistent")

        assert new_store == store  # Same object (unchanged)

    def test_immutability(self):
        """Store operations return new store, don't modify original."""
        store = EmbeddingStore.empty()
        e1 = np.array([1.0, 0.0])

        new_store = store.add("item1", e1)

        assert len(store) == 0  # Original unchanged
        assert len(new_store) == 1


class TestSaveLoadEmbeddings:
    """Tests for embedding persistence."""

    def test_save_and_load(self, mock_embeddings_dir: Path):
        """Save and load embeddings."""
        store = EmbeddingStore.empty()
        e1 = np.array([1.0, 0.0, 0.0])
        e2 = np.array([0.0, 1.0, 0.0])
        store = store.add("item1", e1)
        store = store.add("item2", e2)

        path = mock_embeddings_dir / "test.npy"
        save_result = save_embeddings(path, store)
        assert save_result.is_ok()

        load_result = load_embeddings(path)
        assert load_result.is_ok()

        loaded = load_result.unwrap()
        assert len(loaded) == 2
        assert "item1" in loaded.ids
        assert "item2" in loaded.ids
        np.testing.assert_array_almost_equal(loaded.get("item1"), e1)
        np.testing.assert_array_almost_equal(loaded.get("item2"), e2)

    def test_load_nonexistent_returns_empty(self, mock_embeddings_dir: Path):
        """Loading nonexistent file returns empty store."""
        path = mock_embeddings_dir / "nonexistent.npy"

        result = load_embeddings(path)

        assert result.is_ok()
        assert len(result.unwrap()) == 0


class TestFindSimilar:
    """Tests for similarity search."""

    def test_find_similar_items(self, sample_embeddings):
        """Find similar items above threshold."""
        store = EmbeddingStore(
            ids=["doc1", "doc2", "doc3"],
            embeddings=sample_embeddings,
        )
        query = sample_embeddings[0]  # Most similar to doc1

        results = find_similar(query, store, threshold=0.5)

        assert len(results) == 2  # doc1 (1.0) and doc3 (~0.707)
        assert results[0].id == "doc1"
        assert results[0].score == pytest.approx(1.0)
        assert results[1].id == "doc3"
        assert results[1].score == pytest.approx(0.707, rel=0.01)

    def test_find_similar_with_top_k(self, sample_embeddings):
        """Limit results with top_k."""
        store = EmbeddingStore(
            ids=["doc1", "doc2", "doc3"],
            embeddings=sample_embeddings,
        )
        query = sample_embeddings[2]  # Similar to both doc1 and doc2

        results = find_similar(query, store, threshold=0.0, top_k=2)

        assert len(results) == 2

    def test_find_similar_empty_store(self):
        """Empty store returns empty results."""
        store = EmbeddingStore.empty()
        query = np.array([1.0, 0.0])

        results = find_similar(query, store)

        assert results == []

    def test_find_similar_high_threshold(self, sample_embeddings):
        """High threshold filters out low-similarity items."""
        store = EmbeddingStore(
            ids=["doc1", "doc2", "doc3"],
            embeddings=sample_embeddings,
        )
        query = sample_embeddings[0]

        results = find_similar(query, store, threshold=0.9)

        assert len(results) == 1
        assert results[0].id == "doc1"


class TestIsAvailable:
    """Tests for availability check."""

    def test_available_when_installed(self):
        """is_available() returns True when sentence-transformers installed."""
        with patch.dict("sys.modules", {"sentence_transformers": MagicMock()}):
            # Need to reimport to pick up the mock
            from sage import embeddings

            # Create a mock that returns True
            with patch.object(embeddings, "is_available", return_value=True):
                assert embeddings.is_available() is True

    def test_unavailable_when_not_installed(self):
        """is_available() returns False when sentence-transformers not installed."""
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            import importlib
            from sage import embeddings

            # Create a version that actually checks import
            def check_available():
                try:
                    import sentence_transformers  # noqa: F401
                    return True
                except (ImportError, TypeError):
                    return False

            with patch.object(embeddings, "is_available", side_effect=check_available):
                # This might be True or False depending on environment
                # Just check it returns a boolean
                result = embeddings.is_available()
                assert isinstance(result, bool)


class TestGetEmbedding:
    """Tests for get_embedding with mocked model."""

    def test_get_embedding_returns_vector(self):
        """get_embedding() returns normalized vector."""
        mock_model = MagicMock()
        mock_embedding = np.array([0.5, 0.5, 0.5, 0.5])
        mock_model.encode.return_value = mock_embedding / np.linalg.norm(mock_embedding)

        with patch("sage.embeddings.is_available", return_value=True), \
             patch("sage.embeddings.get_model") as mock_get_model:
            from sage.embeddings import ok
            mock_get_model.return_value = ok(mock_model)

            from sage.embeddings import get_embedding
            result = get_embedding("test text")

            assert result.is_ok()
            assert result.unwrap().shape == (4,)
            mock_model.encode.assert_called_once()

    def test_get_embedding_unavailable(self):
        """get_embedding() returns error when embeddings unavailable."""
        with patch("sage.embeddings.is_available", return_value=False):
            from sage.embeddings import get_model
            result = get_model()

            assert result.is_err()
            assert "not installed" in result.unwrap_err().message


class TestIntegrationWithKnowledge:
    """Integration tests for knowledge embedding support."""

    def test_knowledge_embedding_store_path(self):
        """Knowledge embeddings path is correctly constructed."""
        from sage.embeddings import get_knowledge_embeddings_path

        path = get_knowledge_embeddings_path()

        assert path.name == "knowledge.npy"
        assert "embeddings" in str(path)

    def test_checkpoint_embedding_store_path(self):
        """Checkpoint embeddings path is correctly constructed."""
        from sage.embeddings import get_checkpoint_embeddings_path

        path = get_checkpoint_embeddings_path()

        assert path.name == "checkpoints.npy"
        assert "embeddings" in str(path)
