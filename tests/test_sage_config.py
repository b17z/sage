"""Tests for SageConfig tuning system."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from sage.config import SageConfig, get_sage_config


class TestSageConfigDefaults:
    """Tests for SageConfig default values."""

    def test_default_recall_threshold(self):
        """Default recall threshold is 0.70."""
        cfg = SageConfig()
        assert cfg.recall_threshold == 0.70

    def test_default_dedup_threshold(self):
        """Default dedup threshold is 0.90."""
        cfg = SageConfig()
        assert cfg.dedup_threshold == 0.90

    def test_default_embedding_weight(self):
        """Default embedding weight is 0.70."""
        cfg = SageConfig()
        assert cfg.embedding_weight == 0.70

    def test_default_keyword_weight(self):
        """Default keyword weight is 0.30."""
        cfg = SageConfig()
        assert cfg.keyword_weight == 0.30

    def test_default_topic_drift_threshold(self):
        """Default topic drift threshold is 0.50."""
        cfg = SageConfig()
        assert cfg.topic_drift_threshold == 0.50

    def test_default_embedding_model(self):
        """Default embedding model is BGE-large."""
        cfg = SageConfig()
        assert cfg.embedding_model == "BAAI/bge-large-en-v1.5"

    def test_weights_sum_to_one(self):
        """Embedding + keyword weights sum to 1.0."""
        cfg = SageConfig()
        assert cfg.embedding_weight + cfg.keyword_weight == 1.0


class TestSageConfigLoad:
    """Tests for SageConfig.load()."""

    def test_load_returns_defaults_when_no_file(self, tmp_path: Path):
        """Load returns defaults when config file doesn't exist."""
        cfg = SageConfig.load(tmp_path)

        assert cfg.recall_threshold == 0.70
        assert cfg.dedup_threshold == 0.90

    def test_load_from_yaml_file(self, tmp_path: Path):
        """Load reads values from YAML file."""
        config_path = tmp_path / "tuning.yaml"
        config_path.write_text(yaml.dump({"recall_threshold": 0.65, "dedup_threshold": 0.85}))

        cfg = SageConfig.load(tmp_path)

        assert cfg.recall_threshold == 0.65
        assert cfg.dedup_threshold == 0.85
        # Non-specified values should be defaults
        assert cfg.embedding_weight == 0.70

    def test_load_ignores_unknown_keys(self, tmp_path: Path):
        """Load ignores unknown config keys (security)."""
        config_path = tmp_path / "tuning.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "recall_threshold": 0.65,
                    "malicious_key": "evil_value",
                    "__init__": "should_be_ignored",
                }
            )
        )

        cfg = SageConfig.load(tmp_path)

        assert cfg.recall_threshold == 0.65
        assert not hasattr(cfg, "malicious_key")
        # Verify it's still the correct class (not overridden)
        assert cfg.__class__.__name__ == "SageConfig"

    def test_load_handles_empty_file(self, tmp_path: Path):
        """Load handles empty YAML file gracefully."""
        config_path = tmp_path / "tuning.yaml"
        config_path.write_text("")

        cfg = SageConfig.load(tmp_path)

        assert cfg.recall_threshold == 0.70  # Defaults

    def test_load_handles_null_file(self, tmp_path: Path):
        """Load handles YAML file with just 'null'."""
        config_path = tmp_path / "tuning.yaml"
        config_path.write_text("null")

        cfg = SageConfig.load(tmp_path)

        assert cfg.recall_threshold == 0.70  # Defaults

    def test_load_type_coercion(self, tmp_path: Path):
        """Load correctly handles type coercion from YAML."""
        config_path = tmp_path / "tuning.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "recall_threshold": 0.5,  # Float
                    "depth_min_messages": 10,  # Int
                    "embedding_model": "custom-model",  # String
                }
            )
        )

        cfg = SageConfig.load(tmp_path)

        assert cfg.recall_threshold == 0.5
        assert isinstance(cfg.recall_threshold, float)
        assert cfg.depth_min_messages == 10
        assert isinstance(cfg.depth_min_messages, int)
        assert cfg.embedding_model == "custom-model"


class TestSageConfigSave:
    """Tests for SageConfig.save()."""

    def test_save_creates_directory(self, tmp_path: Path):
        """Save creates sage directory if it doesn't exist."""
        sage_dir = tmp_path / "nested" / ".sage"
        cfg = SageConfig(recall_threshold=0.65)

        path = cfg.save(sage_dir)

        assert sage_dir.exists()
        assert path.exists()

    def test_save_creates_tuning_yaml(self, tmp_path: Path):
        """Save creates tuning.yaml file."""
        sage_dir = tmp_path / ".sage"
        cfg = SageConfig(recall_threshold=0.65)

        path = cfg.save(sage_dir)

        assert path == sage_dir / "tuning.yaml"
        assert path.exists()

    def test_save_only_saves_non_defaults(self, tmp_path: Path):
        """Save only writes values that differ from defaults."""
        sage_dir = tmp_path / ".sage"
        cfg = SageConfig(recall_threshold=0.65)  # Only this differs

        cfg.save(sage_dir)

        with open(sage_dir / "tuning.yaml") as f:
            data = yaml.safe_load(f)

        assert "recall_threshold" in data
        assert data["recall_threshold"] == 0.65
        # Default values should not be in file
        assert "dedup_threshold" not in data
        assert "embedding_weight" not in data

    def test_save_all_defaults_creates_marker(self, tmp_path: Path):
        """Save with all defaults creates version marker."""
        sage_dir = tmp_path / ".sage"
        cfg = SageConfig()  # All defaults

        cfg.save(sage_dir)

        with open(sage_dir / "tuning.yaml") as f:
            data = yaml.safe_load(f)

        assert "_version" in data

    def test_save_roundtrip(self, tmp_path: Path):
        """Save then load preserves values."""
        sage_dir = tmp_path / ".sage"
        original = SageConfig(
            recall_threshold=0.55,
            dedup_threshold=0.85,
            embedding_weight=0.60,
            keyword_weight=0.40,
        )

        original.save(sage_dir)
        loaded = SageConfig.load(sage_dir)

        assert loaded.recall_threshold == 0.55
        assert loaded.dedup_threshold == 0.85
        assert loaded.embedding_weight == 0.60
        assert loaded.keyword_weight == 0.40


class TestSageConfigToDict:
    """Tests for SageConfig.to_dict()."""

    def test_to_dict_includes_all_fields(self):
        """to_dict includes all config fields."""
        cfg = SageConfig()
        d = cfg.to_dict()

        assert "recall_threshold" in d
        assert "dedup_threshold" in d
        assert "embedding_weight" in d
        assert "keyword_weight" in d
        assert "topic_drift_threshold" in d
        assert "convergence_question_drop" in d
        assert "depth_min_messages" in d
        assert "depth_min_tokens" in d
        assert "embedding_model" in d

    def test_to_dict_returns_correct_values(self):
        """to_dict returns correct values."""
        cfg = SageConfig(recall_threshold=0.55)
        d = cfg.to_dict()

        assert d["recall_threshold"] == 0.55
        assert d["dedup_threshold"] == 0.90  # Default


class TestGetSageConfig:
    """Tests for get_sage_config() cascade."""

    @pytest.fixture
    def project_with_config(self, tmp_path: Path):
        """Create a project with .sage/tuning.yaml."""
        project = tmp_path / "my-project"
        sage_dir = project / ".sage"
        sage_dir.mkdir(parents=True)
        (sage_dir / "tuning.yaml").write_text(yaml.dump({"recall_threshold": 0.55}))
        return project

    @pytest.fixture
    def user_sage_dir(self, tmp_path: Path):
        """Create a user-level .sage with config."""
        user_dir = tmp_path / "user-sage"
        user_dir.mkdir()
        (user_dir / "tuning.yaml").write_text(yaml.dump({"recall_threshold": 0.60}))
        return user_dir

    def test_explicit_project_path_used(self, project_with_config: Path):
        """Explicit project_path is used when provided."""
        cfg = get_sage_config(project_path=project_with_config)

        assert cfg.recall_threshold == 0.55

    def test_project_overrides_user(self, project_with_config: Path, user_sage_dir: Path):
        """Project-level config takes priority over user-level."""
        with patch("sage.config.SAGE_DIR", user_sage_dir):
            cfg = get_sage_config(project_path=project_with_config)

        # Should use project (0.55), not user (0.60)
        assert cfg.recall_threshold == 0.55

    def test_falls_back_to_user(self, user_sage_dir: Path):
        """Falls back to user-level when no project."""
        with (
            patch("sage.config.SAGE_DIR", user_sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            cfg = get_sage_config()

        assert cfg.recall_threshold == 0.60

    def test_falls_back_to_defaults(self, tmp_path: Path):
        """Falls back to defaults when no config files exist."""
        empty_sage = tmp_path / "empty-sage"
        empty_sage.mkdir()

        with (
            patch("sage.config.SAGE_DIR", empty_sage),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            cfg = get_sage_config()

        assert cfg.recall_threshold == 0.70  # Default

    def test_auto_detects_project_root(self, tmp_path: Path):
        """Auto-detects project root when not explicitly provided."""
        project = tmp_path / "auto-project"
        sage_dir = project / ".sage"
        sage_dir.mkdir(parents=True)
        (sage_dir / "tuning.yaml").write_text(yaml.dump({"recall_threshold": 0.45}))

        with patch("sage.config.detect_project_root", return_value=project):
            cfg = get_sage_config()

        assert cfg.recall_threshold == 0.45


class TestSageConfigEdgeCases:
    """Edge case tests for SageConfig."""

    def test_threshold_at_zero(self, tmp_path: Path):
        """Threshold of 0.0 is valid and preserved."""
        sage_dir = tmp_path / ".sage"
        cfg = SageConfig(recall_threshold=0.0)

        cfg.save(sage_dir)
        loaded = SageConfig.load(sage_dir)

        assert loaded.recall_threshold == 0.0

    def test_threshold_at_one(self, tmp_path: Path):
        """Threshold of 1.0 is valid and preserved."""
        sage_dir = tmp_path / ".sage"
        cfg = SageConfig(recall_threshold=1.0)

        cfg.save(sage_dir)
        loaded = SageConfig.load(sage_dir)

        assert loaded.recall_threshold == 1.0

    def test_custom_embedding_model(self, tmp_path: Path):
        """Custom embedding model string is preserved."""
        sage_dir = tmp_path / ".sage"
        cfg = SageConfig(embedding_model="mixedbread-ai/mxbai-embed-large-v1")

        cfg.save(sage_dir)
        loaded = SageConfig.load(sage_dir)

        assert loaded.embedding_model == "mixedbread-ai/mxbai-embed-large-v1"

    def test_concurrent_project_and_user_configs(self, tmp_path: Path):
        """Both project and user configs can coexist."""
        project = tmp_path / "project"
        project_sage = project / ".sage"
        project_sage.mkdir(parents=True)
        (project_sage / "tuning.yaml").write_text(yaml.dump({"recall_threshold": 0.50}))

        user_sage = tmp_path / "user"
        user_sage.mkdir()
        (user_sage / "tuning.yaml").write_text(yaml.dump({"recall_threshold": 0.60}))

        # Project config
        project_cfg = get_sage_config(project_path=project)
        assert project_cfg.recall_threshold == 0.50

        # User config (when no project)
        with (
            patch("sage.config.SAGE_DIR", user_sage),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            user_cfg = get_sage_config()
        assert user_cfg.recall_threshold == 0.60


class TestConfigIntegrationKnowledge:
    """Tests verifying config values affect knowledge module behavior."""

    def test_recall_uses_config_threshold(self, tmp_path: Path):
        """recall_knowledge() uses threshold from SageConfig when not specified."""
        from sage.knowledge import (
            add_knowledge,
            recall_knowledge,
        )

        knowledge_dir = tmp_path / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "global").mkdir()
        knowledge_index = knowledge_dir / "index.yaml"

        # Create a tuning config with high threshold
        sage_dir = tmp_path / ".sage"
        (sage_dir / "tuning.yaml").write_text(
            yaml.dump({"recall_threshold": 0.99})  # Very high - nothing should match
        )

        with (
            patch("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir),
            patch("sage.knowledge.KNOWLEDGE_INDEX", knowledge_index),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            add_knowledge(
                content="Test content about Python programming",
                knowledge_id="python-test",
                keywords=["python", "programming"],
            )

            # Without explicit threshold, should use config (0.99 * 10 = 9.9)
            result = recall_knowledge("python", "test")

            # High threshold means nothing matches
            assert result.count == 0

    def test_recall_explicit_threshold_overrides_config(self, tmp_path: Path):
        """Explicit threshold parameter overrides config value."""
        from sage.knowledge import (
            add_knowledge,
            recall_knowledge,
        )

        knowledge_dir = tmp_path / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "global").mkdir()
        knowledge_index = knowledge_dir / "index.yaml"

        sage_dir = tmp_path / ".sage"
        (sage_dir / "tuning.yaml").write_text(yaml.dump({"recall_threshold": 0.99}))  # Very high

        with (
            patch("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir),
            patch("sage.knowledge.KNOWLEDGE_INDEX", knowledge_index),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            add_knowledge(
                content="Test content",
                knowledge_id="override-test",
                keywords=["override"],
            )

            # With explicit low threshold, should match
            result = recall_knowledge("override", "test", threshold=1.0)

            assert result.count == 1

    def test_scoring_uses_config_weights(self, tmp_path: Path):
        """score_item_combined() uses weights from SageConfig."""
        from sage.knowledge import (
            KnowledgeItem,
            KnowledgeMetadata,
            KnowledgeScope,
            KnowledgeTriggers,
            score_item_combined,
        )

        item = KnowledgeItem(
            id="weight-test",
            file="test.md",
            triggers=KnowledgeTriggers(keywords=("test",)),
            scope=KnowledgeScope(),
            metadata=KnowledgeMetadata(added="2026-01-16", source="test", tokens=50),
        )

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        # Test with different weight configurations
        # Config 1: 90% embedding, 10% keyword
        (sage_dir / "tuning.yaml").write_text(
            yaml.dump({"embedding_weight": 0.90, "keyword_weight": 0.10})
        )

        with (
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            # With high embedding weight and high embedding similarity
            score_high_embed = score_item_combined(
                item, "test query", "test", embedding_similarity=0.9
            )

            # With high embedding weight and low embedding similarity
            score_low_embed = score_item_combined(
                item, "test query", "test", embedding_similarity=0.1
            )

            # High embedding similarity should give higher score
            assert score_high_embed > score_low_embed


class TestConfigIntegrationCheckpoint:
    """Tests verifying config values affect checkpoint module behavior."""

    def test_dedup_uses_config_threshold(self, tmp_path: Path):
        """is_duplicate_checkpoint() uses threshold from SageConfig."""
        from sage.checkpoint import Checkpoint, is_duplicate_checkpoint, save_checkpoint

        checkpoints_dir = tmp_path / ".sage" / "checkpoints"
        checkpoints_dir.mkdir(parents=True)
        sage_dir = tmp_path / ".sage"

        # Low threshold - even slightly similar should be duplicate
        (sage_dir / "tuning.yaml").write_text(yaml.dump({"dedup_threshold": 0.1}))  # Very low

        with (
            patch("sage.checkpoint.CHECKPOINTS_DIR", checkpoints_dir),
            patch("sage.checkpoint.SAGE_DIR", sage_dir),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
            patch("sage.checkpoint._add_checkpoint_embedding", return_value=True),
            patch("sage.checkpoint._get_checkpoint_embedding_store") as mock_store,
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_embedding") as mock_get_embed,
            patch("sage.embeddings.cosine_similarity", return_value=0.5),
        ):
            # Setup mock embedding store with one checkpoint
            import numpy as np

            from sage.embeddings import EmbeddingStore

            store = EmbeddingStore.empty().add("existing-cp", np.array([1.0, 0.0, 0.0]))
            mock_store.return_value = store

            # Create a proper mock Result object
            class MockResult:
                def is_err(self):
                    return False

                def unwrap(self):
                    return np.array([0.7, 0.7, 0.0])

            mock_get_embed.return_value = MockResult()

            # Save an existing checkpoint
            existing = Checkpoint(
                id="existing-cp",
                ts="2026-01-15T12:00:00Z",
                trigger="manual",
                core_question="Existing?",
                thesis="Existing thesis about topic A",
                confidence=0.8,
            )
            save_checkpoint(existing)

            # Check if similar thesis is duplicate (with config threshold 0.1)
            # cosine_similarity returns 0.5, threshold is 0.1, so should be duplicate
            result = is_duplicate_checkpoint(
                "Similar thesis about topic A",
                project_path=tmp_path,
            )

            assert result.is_duplicate is True

    def test_dedup_explicit_threshold_overrides_config(self, tmp_path: Path):
        """Explicit threshold parameter overrides config value."""
        from sage.checkpoint import is_duplicate_checkpoint

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        # Low config threshold
        (sage_dir / "tuning.yaml").write_text(yaml.dump({"dedup_threshold": 0.1}))

        with (
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
            patch("sage.embeddings.is_available", return_value=True),
            patch("sage.embeddings.get_embedding") as mock_embed,
            patch("sage.embeddings.cosine_similarity", return_value=0.5),
            patch("sage.checkpoint._get_checkpoint_embedding_store") as mock_store,
            patch("sage.checkpoint.list_checkpoints", return_value=[]),
        ):
            import numpy as np

            from sage.embeddings import EmbeddingStore

            mock_store.return_value = EmbeddingStore.empty()

            # Create a proper mock Result object
            class MockResult:
                def is_err(self):
                    return False

                def unwrap(self):
                    return np.array([1.0])

            mock_embed.return_value = MockResult()

            # With explicit high threshold (0.9), similarity of 0.5 is NOT duplicate
            result = is_duplicate_checkpoint("test thesis", threshold=0.9)

            assert result.is_duplicate is False


class TestConfigCLI:
    """Tests for sage config CLI command."""

    def test_config_list_shows_runtime_and_tuning(self, tmp_path: Path):
        """sage config list shows both runtime and tuning settings."""
        from click.testing import CliRunner

        from sage.cli import main

        runner = CliRunner()

        with (
            patch("sage.config.SAGE_DIR", tmp_path / ".sage"),
            patch("sage.config.CONFIG_PATH", tmp_path / ".sage" / "config.yaml"),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            result = runner.invoke(main, ["config", "list"])

        assert result.exit_code == 0
        assert "Runtime Configuration" in result.output
        assert "Tuning Configuration" in result.output
        assert "recall_threshold" in result.output
        assert "dedup_threshold" in result.output

    def test_config_set_tuning_value(self, tmp_path: Path):
        """sage config set recall_threshold 0.65 updates tuning.yaml."""
        from click.testing import CliRunner

        from sage.cli import main

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        runner = CliRunner()

        with (
            patch("sage.cli.SAGE_DIR", sage_dir),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.CONFIG_PATH", sage_dir / "config.yaml"),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            result = runner.invoke(main, ["config", "set", "recall_threshold", "0.65"])

        assert result.exit_code == 0
        assert "Set recall_threshold = 0.65" in result.output

        # Verify file was written
        tuning_path = sage_dir / "tuning.yaml"
        assert tuning_path.exists()
        content = yaml.safe_load(tuning_path.read_text())
        assert content["recall_threshold"] == 0.65

    def test_config_set_runtime_value(self, tmp_path: Path):
        """sage config set model <value> updates config.yaml."""
        from click.testing import CliRunner

        from sage.cli import main

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)
        config_path = sage_dir / "config.yaml"

        runner = CliRunner()

        with (
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.CONFIG_PATH", config_path),
        ):
            result = runner.invoke(main, ["config", "set", "model", "claude-opus-4"])

        assert result.exit_code == 0
        assert "Set model" in result.output
        assert "runtime config" in result.output

    def test_config_set_project_level(self, tmp_path: Path):
        """sage config set --project creates project-level tuning.yaml."""
        from click.testing import CliRunner

        from sage.cli import main

        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["config", "set", "recall_threshold", "0.55", "--project"])

            assert result.exit_code == 0
            assert "project-level" in result.output

            # Verify project-level file was created
            project_tuning = Path(".sage/tuning.yaml")
            assert project_tuning.exists()
            content = yaml.safe_load(project_tuning.read_text())
            assert content["recall_threshold"] == 0.55

    def test_config_reset(self, tmp_path: Path):
        """sage config reset restores tuning defaults."""
        from click.testing import CliRunner

        from sage.cli import main

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        # Create non-default config
        (sage_dir / "tuning.yaml").write_text(
            yaml.dump({"recall_threshold": 0.42, "dedup_threshold": 0.5})
        )

        runner = CliRunner()

        with (
            patch("sage.cli.SAGE_DIR", sage_dir),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            result = runner.invoke(main, ["config", "reset"])

        assert result.exit_code == 0
        assert "Reset tuning config to defaults" in result.output

        # Verify file now has defaults (only version marker)
        content = yaml.safe_load((sage_dir / "tuning.yaml").read_text())
        assert "recall_threshold" not in content
        assert content.get("_version") == 1

    def test_config_set_unknown_key_fails(self, tmp_path: Path):
        """sage config set with unknown key shows error."""
        from click.testing import CliRunner

        from sage.cli import main

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        runner = CliRunner()

        with (
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.CONFIG_PATH", sage_dir / "config.yaml"),
        ):
            result = runner.invoke(main, ["config", "set", "unknown_key", "value"])

        assert result.exit_code == 1
        assert "Unknown config key" in result.output

    def test_config_shows_non_default_highlighted(self, tmp_path: Path):
        """Non-default tuning values are highlighted in output."""
        from click.testing import CliRunner

        from sage.cli import main

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        # Set a non-default value
        (sage_dir / "tuning.yaml").write_text(yaml.dump({"recall_threshold": 0.42}))

        runner = CliRunner()

        with (
            patch("sage.cli.SAGE_DIR", sage_dir),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.CONFIG_PATH", sage_dir / "config.yaml"),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            result = runner.invoke(main, ["config", "list"])

        assert result.exit_code == 0
        # Non-default value should show "(default: 0.7)"
        assert "0.42" in result.output
        assert "default: 0.7" in result.output


class TestConfigCLIEdgeCases:
    """Edge case tests for config CLI input validation."""

    def test_config_set_float_type_coercion(self, tmp_path: Path):
        """Float values are properly coerced from string input."""
        from click.testing import CliRunner

        from sage.cli import main

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        runner = CliRunner()

        with (
            patch("sage.cli.SAGE_DIR", sage_dir),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            result = runner.invoke(main, ["config", "set", "recall_threshold", "0.75"])

        assert result.exit_code == 0

        # Verify stored as float, not string
        content = yaml.safe_load((sage_dir / "tuning.yaml").read_text())
        assert content["recall_threshold"] == 0.75
        assert isinstance(content["recall_threshold"], float)

    def test_config_set_int_type_coercion(self, tmp_path: Path):
        """Integer values are properly coerced from string input."""
        from click.testing import CliRunner

        from sage.cli import main

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        runner = CliRunner()

        with (
            patch("sage.cli.SAGE_DIR", sage_dir),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            result = runner.invoke(main, ["config", "set", "depth_min_messages", "12"])

        assert result.exit_code == 0

        content = yaml.safe_load((sage_dir / "tuning.yaml").read_text())
        assert content["depth_min_messages"] == 12
        assert isinstance(content["depth_min_messages"], int)

    def test_config_set_invalid_float_fails(self, tmp_path: Path):
        """Invalid float input shows error."""
        from click.testing import CliRunner

        from sage.cli import main

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        runner = CliRunner()

        with (
            patch("sage.cli.SAGE_DIR", sage_dir),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            result = runner.invoke(main, ["config", "set", "recall_threshold", "not_a_number"])

        # Should fail with error
        assert result.exit_code != 0

    def test_config_handles_hyphenated_keys(self, tmp_path: Path):
        """Keys with hyphens are converted to underscores."""
        from click.testing import CliRunner

        from sage.cli import main

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir(parents=True)

        runner = CliRunner()

        with (
            patch("sage.cli.SAGE_DIR", sage_dir),
            patch("sage.config.SAGE_DIR", sage_dir),
            patch("sage.config.detect_project_root", return_value=None),
        ):
            # Use hyphenated key (should work)
            result = runner.invoke(main, ["config", "set", "recall-threshold", "0.65"])

        assert result.exit_code == 0
        assert "recall_threshold" in result.output
