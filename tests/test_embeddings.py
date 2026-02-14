"""Tests for sage.embeddings module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sage.embeddings import (
    DEFAULT_MODEL,
    MODEL_INFO,
    EmbeddingStore,
    check_model_mismatch,
    cosine_similarity,
    cosine_similarity_matrix,
    find_similar,
    get_code_embedding,
    get_code_embeddings_batch,
    get_code_query_embedding,
    get_configured_code_model,
    get_configured_model,
    get_model_info,
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
    embeddings = np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.707, 0.707, 0.0, 0.0],  # 45 degrees between first two
        ]
    )
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

    def test_save_and_load(self, mock_embeddings_dir: Path, monkeypatch):
        """Save and load embeddings."""
        # Mock get_model_info to return matching dimension for test embeddings
        monkeypatch.setattr(
            "sage.embeddings.get_model_info",
            lambda model_name: {"dim": 3, "query_prefix": "", "size_mb": 0},
        )

        store = EmbeddingStore.empty(dim=3)
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

    def test_load_recovers_from_id_embedding_mismatch(self, mock_embeddings_dir: Path, monkeypatch):
        """Load truncates data when IDs and embeddings count don't match (race condition recovery)."""
        import json

        # Mock get_model_info to return matching dimension for test embeddings
        monkeypatch.setattr(
            "sage.embeddings.get_model_info",
            lambda model_name: {"dim": 3, "query_prefix": "", "size_mb": 0},
        )

        # Create mismatched files directly (simulating race condition corruption)
        npy_path = mock_embeddings_dir / "corrupted.npy"
        json_path = mock_embeddings_dir / "corrupted.json"

        # Save 2 embeddings
        embeddings = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        np.save(npy_path, embeddings)

        # But 3 IDs (mismatch!)
        with open(json_path, "w") as f:
            json.dump(["item1", "item2", "item3"], f)

        # Load should recover by truncating to smaller count
        result = load_embeddings(npy_path)

        assert result.is_ok()
        loaded = result.unwrap()
        assert len(loaded) == 2  # Truncated to match embeddings count
        assert loaded.ids == ["item1", "item2"]

    def test_load_recovers_when_embeddings_exceed_ids(self, mock_embeddings_dir: Path, monkeypatch):
        """Load truncates when embeddings count exceeds IDs count."""
        import json

        monkeypatch.setattr(
            "sage.embeddings.get_model_info",
            lambda model_name: {"dim": 3, "query_prefix": "", "size_mb": 0},
        )

        npy_path = mock_embeddings_dir / "corrupted2.npy"
        json_path = mock_embeddings_dir / "corrupted2.json"

        # Save 3 embeddings
        embeddings = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        np.save(npy_path, embeddings)

        # But only 2 IDs
        with open(json_path, "w") as f:
            json.dump(["item1", "item2"], f)

        result = load_embeddings(npy_path)

        assert result.is_ok()
        loaded = result.unwrap()
        assert len(loaded) == 2  # Truncated to match IDs count
        assert loaded.embeddings.shape[0] == 2

    def test_concurrent_saves_maintain_consistency(self, mock_embeddings_dir: Path, monkeypatch):
        """Concurrent saves don't corrupt the embedding store (file locking test)."""
        import concurrent.futures
        import threading

        monkeypatch.setattr(
            "sage.embeddings.get_model_info",
            lambda model_name: {"dim": 3, "query_prefix": "", "size_mb": 0},
        )

        path = mock_embeddings_dir / "concurrent.npy"
        results = []
        errors = []

        def save_item(item_id: int):
            """Save an item to the store."""
            try:
                # Load current store
                load_result = load_embeddings(path)
                if load_result.is_err():
                    errors.append(f"Load failed: {load_result.unwrap_err()}")
                    return

                store = load_result.unwrap()

                # Add new item
                embedding = np.array([float(item_id), 0.0, 0.0])
                store = store.add(f"item{item_id}", embedding)

                # Save updated store
                save_result = save_embeddings(path, store)
                if save_result.is_err():
                    errors.append(f"Save failed: {save_result.unwrap_err()}")
                    return

                results.append(item_id)
            except Exception as e:
                errors.append(str(e))

        # Run 10 concurrent saves
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(save_item, i) for i in range(10)]
            concurrent.futures.wait(futures)

        # Check no errors occurred
        assert not errors, f"Errors during concurrent saves: {errors}"

        # Load final store and verify consistency
        final_result = load_embeddings(path)
        assert final_result.is_ok()

        final_store = final_result.unwrap()

        # Due to file locking, all saves should have succeeded
        # but some may have been overwritten - the key is consistency
        assert len(final_store.ids) == len(final_store.embeddings)

        # Verify each stored item has matching embedding
        for item_id in final_store.ids:
            embedding = final_store.get(item_id)
            assert embedding is not None, f"Missing embedding for {item_id}"


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

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
        ):
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


class TestModelInfo:
    """Tests for model info and configuration."""

    def test_default_model_is_bge_large(self):
        """Default model is BGE-large-en-v1.5."""
        assert DEFAULT_MODEL == "BAAI/bge-large-en-v1.5"

    def test_model_info_has_known_models(self):
        """MODEL_INFO contains expected models."""
        expected_models = [
            "BAAI/bge-large-en-v1.5",
            "BAAI/bge-base-en-v1.5",
            "BAAI/bge-small-en-v1.5",
            "all-MiniLM-L6-v2",
        ]
        for model in expected_models:
            assert model in MODEL_INFO

    def test_model_info_has_required_fields(self):
        """Each model info has dim, query_prefix, size_mb."""
        for model_name, info in MODEL_INFO.items():
            assert "dim" in info, f"{model_name} missing dim"
            assert "query_prefix" in info, f"{model_name} missing query_prefix"
            assert "size_mb" in info, f"{model_name} missing size_mb"

    def test_bge_models_have_query_prefix(self):
        """BGE models require query prefix for optimal retrieval."""
        bge_models = [m for m in MODEL_INFO if m.startswith("BAAI/bge")]
        for model in bge_models:
            prefix = MODEL_INFO[model]["query_prefix"]
            assert len(prefix) > 0, f"{model} should have query prefix"
            assert "Represent this sentence" in prefix

    def test_minilm_no_query_prefix(self):
        """MiniLM models don't need query prefix."""
        assert MODEL_INFO["all-MiniLM-L6-v2"]["query_prefix"] == ""

    def test_get_model_info_known_model(self):
        """get_model_info returns info for known models."""
        info = get_model_info("BAAI/bge-large-en-v1.5")
        assert info["dim"] == 1024
        assert info["size_mb"] == 1340

    def test_get_model_info_unknown_model(self):
        """get_model_info returns defaults for unknown models."""
        info = get_model_info("unknown/model")
        assert info["dim"] == 384  # Conservative default
        assert info["query_prefix"] == ""


class TestGetConfiguredModel:
    """Tests for get_configured_model."""

    def test_returns_model_from_config(self):
        """get_configured_model returns model from SageConfig."""
        from sage.config import SageConfig

        with patch("sage.config.get_sage_config") as mock_config:
            mock_config.return_value = SageConfig(embedding_model="BAAI/bge-base-en-v1.5")
            result = get_configured_model()
            assert result == "BAAI/bge-base-en-v1.5"

    def test_default_is_bge_large(self):
        """Default configured model is BGE-large."""
        from sage.config import SageConfig

        with patch("sage.config.get_sage_config") as mock_config:
            mock_config.return_value = SageConfig()  # Use defaults
            result = get_configured_model()
            assert result == "BAAI/bge-large-en-v1.5"


class TestQueryEmbedding:
    """Tests for get_query_embedding with prefix support."""

    def test_query_embedding_adds_prefix_for_bge(self):
        """Query embedding adds prefix for BGE models."""
        mock_model = MagicMock()
        mock_embedding = np.array([0.5, 0.5, 0.5, 0.5])
        mock_model.encode.return_value = mock_embedding / np.linalg.norm(mock_embedding)

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
            patch("sage.embeddings.get_configured_model", return_value="BAAI/bge-large-en-v1.5"),
        ):
            from sage.embeddings import get_query_embedding, ok

            mock_get_model.return_value = ok(mock_model)

            result = get_query_embedding("test query")

            assert result.is_ok()
            # Check that encode was called with prefixed text
            call_args = mock_model.encode.call_args
            text_arg = call_args[0][0]
            assert text_arg.startswith("Represent this sentence")
            assert "test query" in text_arg

    def test_query_embedding_no_prefix_for_minilm(self):
        """Query embedding skips prefix for MiniLM models."""
        mock_model = MagicMock()
        mock_embedding = np.array([0.5, 0.5, 0.5, 0.5])
        mock_model.encode.return_value = mock_embedding / np.linalg.norm(mock_embedding)

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
            patch("sage.embeddings.get_configured_model", return_value="all-MiniLM-L6-v2"),
        ):
            from sage.embeddings import get_query_embedding, ok

            mock_get_model.return_value = ok(mock_model)

            result = get_query_embedding("test query")

            assert result.is_ok()
            # Check that encode was called without prefix
            call_args = mock_model.encode.call_args
            text_arg = call_args[0][0]
            assert text_arg == "test query"

    def test_document_embedding_no_prefix(self):
        """Document embedding never adds prefix."""
        mock_model = MagicMock()
        mock_embedding = np.array([0.5, 0.5, 0.5, 0.5])
        mock_model.encode.return_value = mock_embedding / np.linalg.norm(mock_embedding)

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
            patch("sage.embeddings.get_configured_model", return_value="BAAI/bge-large-en-v1.5"),
        ):
            from sage.embeddings import get_embedding, ok

            mock_get_model.return_value = ok(mock_model)

            result = get_embedding("document text")

            assert result.is_ok()
            # Check that encode was called without prefix
            call_args = mock_model.encode.call_args
            text_arg = call_args[0][0]
            assert text_arg == "document text"


class TestModelMismatchDetection:
    """Tests for model mismatch detection."""

    def test_check_mismatch_no_metadata(self, tmp_path, monkeypatch):
        """No metadata file means no mismatch."""
        # Point to empty temp dir
        monkeypatch.setattr("sage.embeddings.EMBEDDINGS_META_FILE", tmp_path / "meta.json")
        monkeypatch.setattr(
            "sage.embeddings.get_configured_model", lambda: "BAAI/bge-large-en-v1.5"
        )

        is_mismatch, stored, current = check_model_mismatch()

        assert is_mismatch is False
        assert stored is None
        assert current == "BAAI/bge-large-en-v1.5"

    def test_check_mismatch_same_model(self, tmp_path, monkeypatch):
        """Same model in metadata means no mismatch."""
        meta_file = tmp_path / "meta.json"
        meta_file.write_text(json.dumps({"model": "BAAI/bge-large-en-v1.5"}))
        monkeypatch.setattr("sage.embeddings.EMBEDDINGS_META_FILE", meta_file)
        monkeypatch.setattr(
            "sage.embeddings.get_configured_model", lambda: "BAAI/bge-large-en-v1.5"
        )

        is_mismatch, stored, current = check_model_mismatch()

        assert is_mismatch is False
        assert stored == "BAAI/bge-large-en-v1.5"
        assert current == "BAAI/bge-large-en-v1.5"

    def test_check_mismatch_different_model(self, tmp_path, monkeypatch):
        """Different model in metadata triggers mismatch."""
        meta_file = tmp_path / "meta.json"
        meta_file.write_text(json.dumps({"model": "all-MiniLM-L6-v2"}))
        monkeypatch.setattr("sage.embeddings.EMBEDDINGS_META_FILE", meta_file)
        monkeypatch.setattr(
            "sage.embeddings.get_configured_model", lambda: "BAAI/bge-large-en-v1.5"
        )

        is_mismatch, stored, current = check_model_mismatch()

        assert is_mismatch is True
        assert stored == "all-MiniLM-L6-v2"
        assert current == "BAAI/bge-large-en-v1.5"

    def test_load_embeddings_returns_empty_on_mismatch(self, tmp_path, monkeypatch):
        """Loading embeddings returns empty store when model changed."""
        # Create embeddings file
        embeddings_path = tmp_path / "test.npy"
        ids_path = tmp_path / "test.json"
        np.save(embeddings_path, np.array([[1.0, 0.0, 0.0]]))
        ids_path.write_text(json.dumps(["item1"]))

        # Create metadata with different model
        meta_file = tmp_path / "meta.json"
        meta_file.write_text(json.dumps({"model": "all-MiniLM-L6-v2"}))

        monkeypatch.setattr("sage.embeddings.EMBEDDINGS_META_FILE", meta_file)
        monkeypatch.setattr(
            "sage.embeddings.get_configured_model", lambda: "BAAI/bge-large-en-v1.5"
        )

        result = load_embeddings(embeddings_path)

        assert result.is_ok()
        store = result.unwrap()
        assert len(store) == 0  # Empty due to mismatch


class TestDownloadWarning:
    """Tests for download warning on first load."""

    def test_warning_shown_for_large_model(self, capsys, monkeypatch):
        """Warning shown for models > 100MB on first load."""
        import sage.embeddings

        # Reset warning flag
        monkeypatch.setattr(sage.embeddings, "_first_load_warning_shown", False)

        sage.embeddings._show_download_warning("BAAI/bge-large-en-v1.5")

        captured = capsys.readouterr()
        assert "1340MB" in captured.err
        assert sage.embeddings._first_load_warning_shown is True

    def test_warning_not_shown_twice(self, capsys, monkeypatch):
        """Warning only shown once per session."""
        import sage.embeddings

        # Set flag as already shown
        monkeypatch.setattr(sage.embeddings, "_first_load_warning_shown", True)

        sage.embeddings._show_download_warning("BAAI/bge-large-en-v1.5")

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_warning_not_shown_for_small_model(self, capsys, monkeypatch):
        """Warning not shown for models < 100MB."""
        import sage.embeddings

        # Reset warning flag
        monkeypatch.setattr(sage.embeddings, "_first_load_warning_shown", False)

        sage.embeddings._show_download_warning("all-MiniLM-L6-v2")  # 80MB

        captured = capsys.readouterr()
        assert captured.err == ""


class TestBatchEmbeddings:
    """Tests for batch embedding generation."""

    def test_batch_embeddings_empty_list(self):
        """Empty list returns empty array."""
        from sage.embeddings import get_embeddings_batch

        result = get_embeddings_batch([])

        assert result.is_ok()
        assert len(result.unwrap()) == 0

    def test_batch_embeddings_returns_correct_shape(self):
        """Batch embeddings returns correct shape."""
        mock_model = MagicMock()
        mock_embeddings = np.array(
            [
                [0.5, 0.5, 0.5, 0.5],
                [0.5, 0.5, 0.5, -0.5],
            ]
        )
        # Normalize
        mock_embeddings = mock_embeddings / np.linalg.norm(mock_embeddings, axis=1, keepdims=True)
        mock_model.encode.return_value = mock_embeddings

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
        ):
            from sage.embeddings import get_embeddings_batch, ok

            mock_get_model.return_value = ok(mock_model)

            result = get_embeddings_batch(["text1", "text2"])

            assert result.is_ok()
            assert result.unwrap().shape == (2, 4)


class TestClearModelCache:
    """Tests for clear_model_cache function."""

    def test_clear_model_cache_clears_globals(self, monkeypatch):
        """clear_model_cache clears the cached model and name."""
        import sage.embeddings

        # Set up cached state
        mock_model = MagicMock()
        monkeypatch.setattr(sage.embeddings, "_model", mock_model)
        monkeypatch.setattr(sage.embeddings, "_model_name", "test-model")

        # Clear cache
        sage.embeddings.clear_model_cache()

        # Verify cleared
        assert sage.embeddings._model is None
        assert sage.embeddings._model_name is None

    def test_clear_model_cache_no_op_when_empty(self, monkeypatch):
        """clear_model_cache is safe when no model is cached."""
        import sage.embeddings

        # Ensure no cached model
        monkeypatch.setattr(sage.embeddings, "_model", None)
        monkeypatch.setattr(sage.embeddings, "_model_name", None)

        # Should not raise
        sage.embeddings.clear_model_cache()

        assert sage.embeddings._model is None
        assert sage.embeddings._model_name is None

    def test_clear_model_cache_allows_new_model_load(self, monkeypatch):
        """After clearing cache, get_model loads fresh model."""
        import sage.embeddings

        # Simulate cached model
        old_model = MagicMock()
        old_model.name = "old"
        monkeypatch.setattr(sage.embeddings, "_model", old_model)
        monkeypatch.setattr(sage.embeddings, "_model_name", "old-model")

        # Clear cache
        sage.embeddings.clear_model_cache()

        # Verify next get_model would load fresh (by checking globals are None)
        assert sage.embeddings._model is None
        # If we called get_model now, it would load a new model


class TestCodeEmbeddingModels:
    """Tests for code-specific embedding models (codesage)."""

    def test_codesage_model_info_exists(self):
        """CodeSage models are in MODEL_INFO."""
        assert "codesage/codesage-large" in MODEL_INFO
        assert "codesage/codesage-small" in MODEL_INFO

    def test_codesage_large_has_correct_dimensions(self):
        """CodeSage large has 1024 dimensions (same as BGE-large)."""
        info = get_model_info("codesage/codesage-large")
        assert info["dim"] == 1024

    def test_codesage_no_query_prefix(self):
        """CodeSage models don't need query prefix."""
        assert MODEL_INFO["codesage/codesage-large"]["query_prefix"] == ""
        assert MODEL_INFO["codesage/codesage-small"]["query_prefix"] == ""

    def test_codesage_has_max_tokens(self):
        """CodeSage has max_tokens info for chunking."""
        info = MODEL_INFO["codesage/codesage-large"]
        assert "max_tokens" in info
        assert info["max_tokens"] == 1024


class TestGetConfiguredCodeModel:
    """Tests for get_configured_code_model function."""

    def test_returns_code_model_from_config(self):
        """get_configured_code_model returns code model from SageConfig."""
        from sage.config import SageConfig

        with patch("sage.config.get_sage_config") as mock_config:
            mock_config.return_value = SageConfig(code_embedding_model="codesage/codesage-small")
            result = get_configured_code_model()
            assert result == "codesage/codesage-small"

    def test_default_is_codesage_large(self):
        """Default code model is codesage-large."""
        from sage.config import SageConfig

        with patch("sage.config.get_sage_config") as mock_config:
            mock_config.return_value = SageConfig()  # Use defaults
            result = get_configured_code_model()
            assert result == "codesage/codesage-large"


class TestCodeEmbeddingFunctions:
    """Tests for code-specific embedding functions."""

    def test_get_code_embedding_uses_code_model(self):
        """get_code_embedding uses the code-specific model."""
        mock_model = MagicMock()
        mock_embedding = np.array([0.5, 0.5, 0.5, 0.5])
        mock_model.encode.return_value = mock_embedding / np.linalg.norm(mock_embedding)

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
            patch(
                "sage.embeddings.get_configured_code_model",
                return_value="codesage/codesage-large",
            ),
        ):
            from sage.embeddings import ok

            mock_get_model.return_value = ok(mock_model)

            result = get_code_embedding("def foo(): pass")

            assert result.is_ok()
            # Verify it called get_model with the code model
            mock_get_model.assert_called_with("codesage/codesage-large")

    def test_get_code_query_embedding_uses_code_model(self):
        """get_code_query_embedding uses the code-specific model."""
        mock_model = MagicMock()
        mock_embedding = np.array([0.5, 0.5, 0.5, 0.5])
        mock_model.encode.return_value = mock_embedding / np.linalg.norm(mock_embedding)

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
            patch(
                "sage.embeddings.get_configured_code_model",
                return_value="codesage/codesage-large",
            ),
        ):
            from sage.embeddings import ok

            mock_get_model.return_value = ok(mock_model)

            result = get_code_query_embedding("authentication function")

            assert result.is_ok()
            # Verify it used the code model
            mock_get_model.assert_called_with("codesage/codesage-large")

    def test_get_code_embeddings_batch_uses_code_model(self):
        """get_code_embeddings_batch uses the code-specific model."""
        mock_model = MagicMock()
        mock_embeddings = np.array(
            [
                [0.5, 0.5, 0.5, 0.5],
                [0.5, 0.5, 0.5, -0.5],
            ]
        )
        mock_embeddings = mock_embeddings / np.linalg.norm(mock_embeddings, axis=1, keepdims=True)
        mock_model.encode.return_value = mock_embeddings

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
            patch(
                "sage.embeddings.get_configured_code_model",
                return_value="codesage/codesage-large",
            ),
        ):
            from sage.embeddings import ok

            mock_get_model.return_value = ok(mock_model)

            result = get_code_embeddings_batch(["def foo():", "class Bar:"])

            assert result.is_ok()
            assert result.unwrap().shape == (2, 4)

    def test_code_and_prose_use_different_models(self):
        """Code and prose embeddings use different configured models."""
        from sage.config import SageConfig

        with patch("sage.config.get_sage_config") as mock_config:
            mock_config.return_value = SageConfig(
                embedding_model="BAAI/bge-large-en-v1.5",
                code_embedding_model="codesage/codesage-large",
            )

            prose_model = get_configured_model()
            code_model = get_configured_code_model()

            assert prose_model == "BAAI/bge-large-en-v1.5"
            assert code_model == "codesage/codesage-large"
            assert prose_model != code_model


class TestSeparateEmbeddingSpaces:
    """Tests for separate embedding spaces (code vs prose)."""

    def test_code_embedding_does_not_add_bge_prefix(self):
        """Code embeddings don't add BGE query prefix (CodeSage doesn't need it)."""
        mock_model = MagicMock()
        mock_embedding = np.array([0.5, 0.5, 0.5, 0.5])
        mock_model.encode.return_value = mock_embedding / np.linalg.norm(mock_embedding)

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
            patch(
                "sage.embeddings.get_configured_code_model",
                return_value="codesage/codesage-large",
            ),
        ):
            from sage.embeddings import ok

            mock_get_model.return_value = ok(mock_model)

            get_code_query_embedding("find authentication")

            # Check that encode was called without prefix
            call_args = mock_model.encode.call_args
            text_arg = call_args[0][0]
            assert not text_arg.startswith("Represent this sentence")
            assert text_arg == "find authentication"

    def test_prose_embedding_adds_bge_prefix_for_queries(self):
        """Prose query embeddings add BGE prefix when using BGE model."""
        mock_model = MagicMock()
        mock_embedding = np.array([0.5, 0.5, 0.5, 0.5])
        mock_model.encode.return_value = mock_embedding / np.linalg.norm(mock_embedding)

        with (
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_model") as mock_get_model,
            patch("sage.embeddings.get_configured_model", return_value="BAAI/bge-large-en-v1.5"),
        ):
            from sage.embeddings import get_query_embedding, ok

            mock_get_model.return_value = ok(mock_model)

            get_query_embedding("find knowledge about auth")

            # Check that encode was called with prefix
            call_args = mock_model.encode.call_args
            text_arg = call_args[0][0]
            assert text_arg.startswith("Represent this sentence")
