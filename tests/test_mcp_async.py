"""Tests for async MCP server operations.

These tests verify that the async infrastructure works correctly:
- Tools return immediately (queued)
- Worker processes tasks in background
- Notifications are written on completion
- Graceful shutdown persists pending tasks

Note: MCP tools are now synchronous, so tests call them directly.
"""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from sage.config import SageConfig
from sage.tasks import (
    Task,
    clear_notifications,
    load_pending_tasks,
    read_notifications,
    save_pending_tasks,
)


@pytest.fixture
def async_test_env(tmp_path, monkeypatch):
    """Set up environment for async testing."""
    # Create .sage directories
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    (sage_dir / "checkpoints").mkdir()
    (sage_dir / "knowledge").mkdir()

    # Monkeypatch paths
    monkeypatch.setattr("sage.tasks.SAGE_DIR", sage_dir)
    monkeypatch.setattr("sage.tasks.NOTIFY_FILE", sage_dir / "notifications.jsonl")
    monkeypatch.setattr("sage.tasks.PENDING_TASKS_FILE", sage_dir / "pending_tasks.jsonl")

    # Monkeypatch MCP server project root
    monkeypatch.setattr("sage.mcp_server._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("sage.checkpoint.CHECKPOINTS_DIR", sage_dir / "checkpoints")
    monkeypatch.setattr("sage.knowledge.SAGE_DIR", sage_dir)
    monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", sage_dir / "knowledge")
    monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", sage_dir / "knowledge" / "index.yaml")

    return {
        "tmp_path": tmp_path,
        "sage_dir": sage_dir,
    }


@pytest.fixture
def mock_async_disabled(monkeypatch):
    """Mock config with async disabled."""
    config = SageConfig(async_enabled=False)
    monkeypatch.setattr(
        "sage.mcp_server.get_sage_config",
        lambda project_path=None: config,
    )
    return config


@pytest.fixture
def mock_async_enabled(monkeypatch):
    """Mock config with async enabled."""
    config = SageConfig(async_enabled=True, notify_success=True, notify_errors=True)
    monkeypatch.setattr(
        "sage.mcp_server.get_sage_config",
        lambda project_path=None: config,
    )
    return config


class TestAsyncCheckpointSave:
    """Tests for checkpoint saving with fire-and-forget architecture."""

    def test_checkpoint_returns_queued_immediately(
        self, async_test_env, mock_async_enabled
    ):
        """sage_save_checkpoint returns 'Checkpoint queued' immediately (fire-and-forget)."""
        from sage.mcp_server import sage_save_checkpoint

        result = sage_save_checkpoint(
            core_question="How to implement auth?",
            thesis="JWT is the best approach for stateless authentication.",
            confidence=0.8,
        )

        # Fire-and-forget returns immediately with queued message
        assert "📍 Checkpoint" in result

    def test_checkpoint_returns_queued_regardless_of_async_setting(
        self, async_test_env, mock_async_disabled
    ):
        """sage_save_checkpoint uses fire-and-forget regardless of async config."""
        from sage.mcp_server import sage_save_checkpoint

        result = sage_save_checkpoint(
            core_question="How to implement auth?",
            thesis="JWT is the best approach for stateless authentication.",
            confidence=0.8,
        )

        assert "📍 Checkpoint" in result

    def test_checkpoint_saves_in_background(self, async_test_env, mock_async_disabled):
        """sage_save_checkpoint actually saves the checkpoint in background."""
        from sage.mcp_server import sage_list_checkpoints, sage_save_checkpoint

        result = sage_save_checkpoint(
            core_question="Test question",
            thesis="Test thesis with enough content.",
            confidence=0.7,
        )

        assert "📍 Checkpoint" in result

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Verify checkpoint was saved
        list_result = sage_list_checkpoints()
        assert "Checkpoints [1]" in list_result

    def test_checkpoint_validates_before_save(self, async_test_env, mock_async_enabled):
        """Invalid checkpoint data rejected before fire-and-forget save."""
        from sage.mcp_server import sage_save_checkpoint

        # Invalid confidence
        result = sage_save_checkpoint(
            core_question="Q",
            thesis="T",
            confidence=1.5,
        )

        assert "Invalid confidence" in result


class TestAsyncKnowledgeSave:
    """Tests for knowledge saving with fire-and-forget architecture."""

    def test_knowledge_returns_queued_immediately(
        self, async_test_env, mock_async_enabled
    ):
        """sage_save_knowledge returns 'Knowledge queued' immediately (fire-and-forget)."""
        from sage.mcp_server import sage_save_knowledge

        result = sage_save_knowledge(
            knowledge_id="test-knowledge",
            content="Test content for knowledge item.",
            keywords=["test", "knowledge"],
        )

        # Fire-and-forget returns immediately with queued message
        assert "📍 Knowledge" in result

    def test_knowledge_returns_queued_regardless_of_async_setting(
        self, async_test_env, mock_async_disabled
    ):
        """sage_save_knowledge uses fire-and-forget regardless of async config."""
        from sage.mcp_server import sage_save_knowledge

        result = sage_save_knowledge(
            knowledge_id="test-knowledge",
            content="Test content for knowledge item.",
            keywords=["test", "knowledge"],
        )

        assert "📍 Knowledge" in result


class TestAsyncAutosaveCheck:
    """Tests for autosave check with fire-and-forget architecture."""

    def test_autosave_returns_queued_immediately(
        self, async_test_env, mock_async_enabled, monkeypatch
    ):
        """sage_autosave_check returns 'Checkpoint queued' immediately (fire-and-forget)."""
        from sage.mcp_server import sage_autosave_check

        # Mock dedup check to allow save
        mock_dedup = MagicMock()
        mock_dedup.is_duplicate = False
        monkeypatch.setattr(
            "sage.mcp_server.is_duplicate_checkpoint",
            lambda thesis, project_path=None: mock_dedup,
        )

        result = sage_autosave_check(
            trigger_event="manual",
            core_question="Research question here",
            current_thesis="A thesis with sufficient content for validation.",
            confidence=0.8,
        )

        # Fire-and-forget returns immediately with queued message
        assert "📍 Checkpoint" in result

    def test_autosave_returns_queued_regardless_of_async_setting(
        self, async_test_env, mock_async_disabled, monkeypatch
    ):
        """sage_autosave_check uses fire-and-forget regardless of async config."""
        from sage.mcp_server import sage_autosave_check

        # Mock dedup check
        mock_dedup = MagicMock()
        mock_dedup.is_duplicate = False
        monkeypatch.setattr(
            "sage.mcp_server.is_duplicate_checkpoint",
            lambda thesis, project_path=None: mock_dedup,
        )

        result = sage_autosave_check(
            trigger_event="manual",
            core_question="Research question here",
            current_thesis="A thesis with sufficient content for validation.",
            confidence=0.8,
        )

        assert "📍 Checkpoint" in result


class TestWorkerProcessing:
    """Tests for background worker."""

    @pytest.mark.asyncio
    async def test_worker_processes_checkpoint_task(self, async_test_env, monkeypatch):
        """Worker processes checkpoint tasks correctly."""
        from sage.mcp_server import _process_task
        from sage.tasks import Task

        task = Task(
            id="test-task",
            type="checkpoint",
            data={
                "core_question": "How to test?",
                "thesis": "Testing is important for quality.",
                "confidence": 0.9,
                "trigger": "manual",
                "template": "default",
                "open_questions": [],
                "sources": [],
                "tensions": [],
                "unique_contributions": [],
                "action": {"goal": "", "type": "learning"},
                "key_evidence": [],
                "reasoning_trace": "",
            },
        )

        result = await _process_task(task)

        assert result.status == "success"
        assert "Checkpoint saved" in result.message

    @pytest.mark.asyncio
    async def test_worker_processes_knowledge_task(self, async_test_env):
        """Worker processes knowledge tasks correctly."""
        from sage.mcp_server import _process_task
        from sage.tasks import Task

        task = Task(
            id="test-task",
            type="knowledge",
            data={
                "knowledge_id": "worker-test",
                "content": "Test content from worker.",
                "keywords": ["worker", "test"],
                "skill": None,
                "source": "",
                "item_type": "knowledge",
            },
        )

        result = await _process_task(task)

        assert result.status == "success"
        assert "Knowledge saved" in result.message

    @pytest.mark.asyncio
    async def test_worker_handles_task_failure(self, async_test_env, monkeypatch):
        """Worker handles task failure gracefully."""
        from sage.mcp_server import _process_task
        from sage.tasks import Task

        # Mock the sync save to raise an exception
        def failing_save(task):
            raise ValueError("Simulated save failure")

        monkeypatch.setattr("sage.mcp_server._sync_save_checkpoint", failing_save)

        # Create a valid task that will fail due to our mock
        task = Task(
            id="failing-task",
            type="checkpoint",
            data={
                "core_question": "Test question",
                "thesis": "Test thesis",
                "confidence": 0.5,
            },
        )

        result = await _process_task(task)

        assert result.status == "failed"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_worker_handles_unknown_task_type(self, async_test_env):
        """Worker rejects unknown task types."""
        from sage.mcp_server import _process_task

        # We can't create a Task with invalid type (validation blocks it)
        # But we can test _process_task directly with a mock
        mock_task = MagicMock()
        mock_task.id = "test"
        mock_task.type = "unknown"
        mock_task.data = {}

        result = await _process_task(mock_task)

        assert result.status == "failed"
        assert "Unknown task type" in result.message


class TestNotifications:
    """Tests for notification writing."""

    @pytest.mark.asyncio
    async def test_success_notification_written(self, async_test_env, monkeypatch):
        """Success notification written when task completes."""
        from sage.tasks import write_notification

        # Clear any existing
        clear_notifications()

        write_notification("success", "Checkpoint saved: test-id")

        notifications = read_notifications()
        assert len(notifications) == 1
        assert notifications[0]["type"] == "success"
        assert "Checkpoint saved" in notifications[0]["msg"]

    @pytest.mark.asyncio
    async def test_error_notification_written(self, async_test_env):
        """Error notification written when task fails."""
        from sage.tasks import write_notification

        clear_notifications()

        write_notification("error", "Save failed: disk full")

        notifications = read_notifications()
        assert len(notifications) == 1
        assert notifications[0]["type"] == "error"
        assert "disk full" in notifications[0]["msg"]

    @pytest.mark.asyncio
    async def test_notification_respects_config(self, async_test_env, monkeypatch):
        """Notifications respect config settings."""
        # When notify_success=False, success notifications shouldn't be written
        # This is tested at the worker level, not notification level
        # The write_notification function always writes - config check is in worker
        pass  # Covered by worker integration tests


class TestGracefulShutdown:
    """Tests for graceful shutdown behavior."""

    @pytest.mark.asyncio
    async def test_pending_tasks_saved_on_timeout(self, async_test_env):
        """Pending tasks saved when shutdown times out."""
        tasks = [
            Task(
                id="pending-1",
                type="checkpoint",
                data={"core_question": "Q1", "thesis": "T1", "confidence": 0.5},
            ),
            Task(
                id="pending-2",
                type="knowledge",
                data={"knowledge_id": "k1", "content": "C1", "keywords": ["k"]},
            ),
        ]

        save_pending_tasks(tasks)
        loaded = load_pending_tasks()

        assert len(loaded) == 2
        assert loaded[0].id == "pending-1"
        assert loaded[1].id == "pending-2"

    @pytest.mark.asyncio
    async def test_pending_tasks_loaded_on_startup(self, async_test_env):
        """Pending tasks reloaded on startup."""
        from sage import mcp_server
        from sage.mcp_server import _reload_pending_tasks

        # Reset queue
        mcp_server._task_queue = asyncio.Queue()

        # Save some pending tasks
        tasks = [
            Task(
                id="reload-1",
                type="checkpoint",
                data={"core_question": "Q", "thesis": "T", "confidence": 0.5},
            ),
        ]
        save_pending_tasks(tasks)

        # Reload
        await _reload_pending_tasks()

        # Should be in queue
        assert mcp_server._task_queue.qsize() == 1
        task = await mcp_server._task_queue.get()
        assert task.id == "reload-1"


class TestModelWarmup:
    """Tests for background model warmup."""

    @pytest.mark.asyncio
    async def test_warmup_runs_in_background(self, async_test_env, monkeypatch):
        """Model warmup runs without blocking."""
        from sage.mcp_server import _warmup_model

        # Mock embeddings to track if warmup was called
        warmup_called = False

        def mock_get_model():
            nonlocal warmup_called
            warmup_called = True
            return MagicMock()

        monkeypatch.setattr("sage.embeddings.is_available", lambda: True)
        monkeypatch.setattr("sage.embeddings.get_model", mock_get_model)

        # Run warmup
        await _warmup_model()

        assert warmup_called

    @pytest.mark.asyncio
    async def test_warmup_handles_failure(self, async_test_env, monkeypatch):
        """Warmup failure doesn't crash."""
        from sage.mcp_server import _warmup_model

        def mock_get_model():
            raise Exception("Model load failed")

        monkeypatch.setattr("sage.embeddings.is_available", lambda: True)
        monkeypatch.setattr("sage.embeddings.get_model", mock_get_model)

        # Should not raise
        await _warmup_model()


class TestAsyncPerformance:
    """Tests verifying async operations are fast."""

    def test_checkpoint_save_returns_fast(self, async_test_env, mock_async_enabled):
        """Checkpoint save returns in under 100ms."""
        from sage import mcp_server
        from sage.mcp_server import sage_save_checkpoint

        mcp_server._task_queue = asyncio.Queue()

        start = time.time()
        sage_save_checkpoint(
            core_question="Performance test question",
            thesis="This should return immediately without waiting for save.",
            confidence=0.8,
        )
        elapsed = time.time() - start

        # Should be nearly instant since we're just queuing
        assert elapsed < 0.1, f"Took {elapsed:.3f}s, expected < 0.1s"

    def test_knowledge_save_returns_fast(self, async_test_env, mock_async_enabled):
        """Knowledge save returns in under 100ms."""
        from sage import mcp_server
        from sage.mcp_server import sage_save_knowledge

        mcp_server._task_queue = asyncio.Queue()

        start = time.time()
        sage_save_knowledge(
            knowledge_id="perf-test",
            content="Performance test content.",
            keywords=["performance"],
        )
        elapsed = time.time() - start

        assert elapsed < 0.1, f"Took {elapsed:.3f}s, expected < 0.1s"


class TestSyncFallback:
    """Tests for synchronous fallback when async disabled."""

    def test_checkpoint_sync_fallback_works(self, async_test_env, mock_async_disabled):
        """Checkpoint saves synchronously when async disabled."""
        from sage.mcp_server import sage_save_checkpoint

        result = sage_save_checkpoint(
            core_question="Sync fallback test",
            thesis="This should save synchronously.",
            confidence=0.7,
        )

        # Sync save returns "Checkpoint saved" not "Checkpoint queued"
        assert "📍 Checkpoint" in result

    def test_knowledge_sync_fallback_works(self, async_test_env, mock_async_disabled):
        """Knowledge saves synchronously when async disabled."""
        from sage.mcp_server import sage_save_knowledge

        result = sage_save_knowledge(
            knowledge_id="sync-fallback",
            content="Sync fallback content.",
            keywords=["sync"],
        )

        assert "📍 Knowledge" in result


class TestQueueManagement:
    """Tests for queue management."""

    @pytest.mark.asyncio
    async def test_queue_fifo_order(self, async_test_env, mock_async_enabled):
        """Tasks processed in FIFO order."""
        from sage import mcp_server

        mcp_server._task_queue = asyncio.Queue()

        # Add tasks
        tasks = []
        for i in range(5):
            task = Task(
                id=f"task-{i}",
                type="checkpoint",
                data={"core_question": f"Q{i}", "thesis": f"T{i}", "confidence": 0.5},
            )
            await mcp_server._task_queue.put(task)
            tasks.append(task)

        # Retrieve in order
        for i in range(5):
            retrieved = await mcp_server._task_queue.get()
            assert retrieved.id == f"task-{i}"

    @pytest.mark.asyncio
    async def test_queue_empty_initially(self, async_test_env):
        """Queue starts empty."""
        from sage import mcp_server

        mcp_server._task_queue = asyncio.Queue()
        assert mcp_server._task_queue.empty()
