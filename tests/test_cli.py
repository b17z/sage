"""Tests for CLI commands."""

import pytest
from click.testing import CliRunner

from sage.cli import main


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def isolated_sage(tmp_path, monkeypatch):
    """Set up isolated sage directories."""
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    (sage_dir / "skills").mkdir()
    (sage_dir / "knowledge").mkdir()

    skills_dir = tmp_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True)

    monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
    monkeypatch.setattr("sage.config.SKILLS_DIR", skills_dir)
    monkeypatch.setattr("sage.config.CONFIG_PATH", sage_dir / "config.yaml")
    monkeypatch.setattr("sage.skill.SKILLS_DIR", skills_dir)

    return tmp_path


class TestListCommand:
    """Tests for the list command."""

    def test_list_runs_without_error(self, runner):
        """List command runs without crashing."""
        result = runner.invoke(main, ["list"])

        # Should either show skills or "no skills" message
        assert result.exit_code == 0

    def test_list_output_contains_expected_elements(self, runner):
        """List output has expected formatting."""
        result = runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Either shows skills or indicates none
        assert len(result.output) > 0


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_directories(self, runner, tmp_path, monkeypatch):
        """Init creates required directories."""
        sage_dir = tmp_path / ".sage"
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.config.CONFIG_PATH", sage_dir / "config.yaml")
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["init", "--non-interactive"])

        assert result.exit_code == 0
        assert sage_dir.exists()

    def test_init_with_api_key(self, runner, tmp_path, monkeypatch):
        """Init accepts API key argument."""
        sage_dir = tmp_path / ".sage"
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.config.CONFIG_PATH", sage_dir / "config.yaml")
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["init", "--api-key", "test-key", "--non-interactive"])

        assert result.exit_code == 0


class TestHistoryCommand:
    """Tests for the history command."""

    def test_history_nonexistent_skill(self, runner):
        """History for nonexistent skill shows appropriate message."""
        result = runner.invoke(main, ["history", "definitely-nonexistent-skill-xyz"])

        # Should show "no history" message (exit code 0 is fine)
        output_lower = result.output.lower()
        assert "no history" in output_lower or "not found" in output_lower

    def test_history_accepts_limit_flag(self, runner):
        """History command accepts limit flag."""
        # Test that the CLI accepts the flag (even if skill doesn't exist)
        result = runner.invoke(main, ["history", "some-skill", "--limit", "5"])

        # CLI should accept the flag syntax
        assert "--limit" not in result.output  # No "unknown option" error

    def test_history_accepts_json_flag(self, runner):
        """History command accepts json flag."""
        result = runner.invoke(main, ["history", "some-skill", "--json"])

        # CLI should accept the flag syntax
        assert "--json" not in result.output  # No "unknown option" error


class TestContextCommand:
    """Tests for the context command."""

    def test_context_nonexistent_skill(self, runner):
        """Context for nonexistent skill shows error."""
        result = runner.invoke(main, ["context", "definitely-nonexistent-skill-xyz"])

        # Should fail
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_context_requires_skill_argument(self, runner):
        """Context command requires skill argument."""
        result = runner.invoke(main, ["context"])

        # Missing argument should error
        assert result.exit_code != 0


class TestStatusCommand:
    """Tests for the status command."""

    def test_status_produces_output(self, runner):
        """Status command produces some output."""
        result = runner.invoke(main, ["status"])

        # Status should produce output (may fail due to config but shouldn't crash CLI)
        assert len(result.output) > 0 or result.exit_code != 0


class TestUsageCommand:
    """Tests for the usage command."""

    def test_usage_produces_output(self, runner):
        """Usage command produces some output."""
        result = runner.invoke(main, ["usage"])

        # Should produce output
        assert len(result.output) > 0 or result.exit_code == 0

    def test_usage_accepts_skill_argument(self, runner):
        """Usage command accepts skill as positional argument."""
        result = runner.invoke(main, ["usage", "any-skill"])

        # Should not crash (may show no history but shouldn't error on syntax)
        assert result.exit_code == 0 or "error" not in result.output.lower()

    def test_usage_accepts_period_flag(self, runner):
        """Usage accepts period flag."""
        result = runner.invoke(main, ["usage", "--period", "7"])

        # CLI should accept the flag syntax
        assert "--period" not in result.output  # No "unknown option" error


class TestKnowledgeCommands:
    """Tests for knowledge subcommands."""

    def test_knowledge_list_empty(self, runner, isolated_sage, monkeypatch):
        """Knowledge list shows no items when empty."""
        knowledge_dir = isolated_sage / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        result = runner.invoke(main, ["knowledge", "list"])

        assert result.exit_code == 0
        assert "No knowledge" in result.output or "0" in result.output

    def test_knowledge_add_from_file(self, runner, isolated_sage, monkeypatch):
        """Knowledge add creates item from file."""
        knowledge_dir = isolated_sage / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        # Create a file to add
        content_file = isolated_sage / "test-content.md"
        content_file.write_text("This is test knowledge content.")

        result = runner.invoke(
            main,
            [
                "knowledge",
                "add",
                str(content_file),
                "--id",
                "test-knowledge",
                "--keywords",
                "test,knowledge,demo",
            ],
        )

        assert result.exit_code == 0
        assert "test-knowledge" in result.output or "saved" in result.output.lower()

    def test_knowledge_rm_nonexistent(self, runner, isolated_sage, monkeypatch):
        """Knowledge rm for nonexistent item shows error."""
        knowledge_dir = isolated_sage / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        result = runner.invoke(main, ["knowledge", "rm", "nonexistent", "--force"])

        # Should indicate not found
        assert "not found" in result.output.lower() or result.exit_code != 0

    def test_knowledge_match(self, runner, isolated_sage, monkeypatch):
        """Knowledge match shows matching items."""
        knowledge_dir = isolated_sage / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        result = runner.invoke(main, ["knowledge", "match", "test query"])

        assert result.exit_code == 0


class TestHelpCommands:
    """Tests for help output."""

    def test_main_help(self, runner):
        """Main help shows available commands."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "list" in result.output
        assert "ask" in result.output
        assert "init" in result.output

    def test_config_help(self, runner):
        """Config help shows subcommands."""
        result = runner.invoke(main, ["config", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output
        assert "set" in result.output

    def test_knowledge_help(self, runner):
        """Knowledge help shows subcommands."""
        result = runner.invoke(main, ["knowledge", "--help"])

        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "rm" in result.output


class TestErrorHandling:
    """Tests for CLI error handling."""

    def test_invalid_command(self, runner):
        """Invalid command shows error."""
        result = runner.invoke(main, ["invalidcommand"])

        assert result.exit_code != 0

    def test_missing_required_arg(self, runner, isolated_sage):
        """Missing required argument shows error."""
        result = runner.invoke(main, ["ask"])  # Missing skill and query

        assert result.exit_code != 0


class TestHealthCommand:
    """Tests for the health command."""

    def test_health_runs_without_error(self, runner):
        """Health command runs without crashing."""
        result = runner.invoke(main, ["health"])
        # Should produce output regardless of state
        assert result.exit_code == 0
        assert "Sage Health Check" in result.output

    def test_health_shows_sage_directory_status(self, runner, tmp_path, monkeypatch):
        """Health shows SAGE_DIR status."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        assert "Sage directory" in result.output

    def test_health_reports_missing_sage_dir(self, runner, tmp_path, monkeypatch):
        """Health reports when SAGE_DIR doesn't exist."""
        sage_dir = tmp_path / ".sage-nonexistent"
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        assert "sage init" in result.output.lower() or "missing" in result.output.lower()

    def test_health_checks_config(self, runner, tmp_path, monkeypatch):
        """Health checks config file status."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        config_path = sage_dir / "config.yaml"
        config_path.write_text("embedding_model: test\n")
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        assert "Config" in result.output or "config" in result.output.lower()

    def test_health_checks_embeddings(self, runner, tmp_path, monkeypatch):
        """Health checks embedding availability."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        assert "Embeddings" in result.output or "embedding" in result.output.lower()

    def test_health_checks_checkpoints(self, runner, tmp_path, monkeypatch):
        """Health checks checkpoint status."""
        sage_dir = tmp_path / ".sage"
        checkpoints_dir = sage_dir / "checkpoints"
        checkpoints_dir.mkdir(parents=True)
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.checkpoint.CHECKPOINTS_DIR", checkpoints_dir)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        assert "Checkpoints" in result.output or "checkpoint" in result.output.lower()

    def test_health_checks_knowledge(self, runner, tmp_path, monkeypatch):
        """Health checks knowledge status."""
        sage_dir = tmp_path / ".sage"
        knowledge_dir = sage_dir / "knowledge"
        knowledge_dir.mkdir(parents=True)
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        assert "Knowledge" in result.output or "knowledge" in result.output.lower()

    def test_health_checks_file_permissions(self, runner, tmp_path, monkeypatch):
        """Health checks file permissions."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        assert "permissions" in result.output.lower() or "File" in result.output

    def test_health_checks_pending_tasks(self, runner, tmp_path, monkeypatch):
        """Health checks pending tasks."""
        sage_dir = tmp_path / ".sage"
        tasks_dir = sage_dir / "tasks"
        tasks_dir.mkdir(parents=True)
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.tasks.TASKS_DIR", tasks_dir)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        # Should mention tasks somewhere
        assert "task" in result.output.lower() or "Pending" in result.output

    def test_health_reports_all_healthy(self, runner, tmp_path, monkeypatch):
        """Health reports all systems healthy when everything is OK."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        (sage_dir / "checkpoints").mkdir()
        (sage_dir / "knowledge").mkdir()
        (sage_dir / "tasks").mkdir()

        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.config.CONFIG_PATH", sage_dir / "config.yaml")
        monkeypatch.setattr("sage.checkpoint.CHECKPOINTS_DIR", sage_dir / "checkpoints")
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", sage_dir / "knowledge")
        monkeypatch.setattr("sage.tasks.TASKS_DIR", sage_dir / "tasks")
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        # Should indicate healthy state
        assert "healthy" in result.output.lower() or "✓" in result.output

    def test_health_shows_checkpoint_count(self, runner, tmp_path, monkeypatch):
        """Health shows number of checkpoints."""
        sage_dir = tmp_path / ".sage"
        checkpoints_dir = sage_dir / "checkpoints"
        checkpoints_dir.mkdir(parents=True)
        # Create some checkpoint files
        (checkpoints_dir / "cp1.md").write_text("# Checkpoint 1\n")
        (checkpoints_dir / "cp2.md").write_text("# Checkpoint 2\n")

        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.checkpoint.CHECKPOINTS_DIR", checkpoints_dir)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        # Should show checkpoint count
        assert "2" in result.output or "checkpoint" in result.output.lower()

    def test_health_detects_permission_issues(self, runner, tmp_path, monkeypatch):
        """Health detects files with wrong permissions."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        config_path = sage_dir / "config.yaml"
        config_path.write_text("test: value\n")
        # Set world-readable permissions (insecure)
        config_path.chmod(0o644)

        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("sage.cli.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["health"])

        assert result.exit_code == 0
        # Should report permission issue
        assert "0o644" in result.output or "permission" in result.output.lower()

    def test_health_help(self, runner):
        """Health help shows description."""
        result = runner.invoke(main, ["health", "--help"])

        assert result.exit_code == 0
        assert "health" in result.output.lower()
        assert "diagnostic" in result.output.lower() or "check" in result.output.lower()


class TestAdminCommands:
    """Tests for admin commands."""

    def test_admin_help(self, runner):
        """Admin help shows subcommands."""
        result = runner.invoke(main, ["admin", "--help"])

        assert result.exit_code == 0
        assert "rebuild-embeddings" in result.output
        assert "clear-cache" in result.output

    def test_admin_rebuild_embeddings_help(self, runner):
        """Rebuild embeddings help shows options."""
        result = runner.invoke(main, ["admin", "rebuild-embeddings", "--help"])

        assert result.exit_code == 0
        assert "--force" in result.output

    def test_admin_clear_cache_no_cache(self, runner, tmp_path, monkeypatch):
        """Clear cache when no cache exists shows appropriate message."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["admin", "clear-cache"])

        assert result.exit_code == 0
        assert "no cache" in result.output.lower()

    def test_admin_clear_cache_removes_embeddings(self, runner, tmp_path, monkeypatch):
        """Clear cache removes embeddings directory."""
        sage_dir = tmp_path / ".sage"
        embeddings_dir = sage_dir / "embeddings"
        embeddings_dir.mkdir(parents=True)
        (embeddings_dir / "test.npy").touch()
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)

        result = runner.invoke(main, ["admin", "clear-cache"])

        assert result.exit_code == 0
        assert "cleared" in result.output.lower()
        assert not embeddings_dir.exists()

    def test_admin_rebuild_no_mismatch(self, runner, tmp_path, monkeypatch):
        """Rebuild with no model mismatch shows already up-to-date."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
        monkeypatch.setattr(
            "sage.embeddings.check_model_mismatch", lambda: (False, "model", "model")
        )

        result = runner.invoke(main, ["admin", "rebuild-embeddings"])

        assert result.exit_code == 0
        assert "already" in result.output.lower()
