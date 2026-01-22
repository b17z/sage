"""Sage MCP Server.

Exposes checkpoint and knowledge operations as MCP tools for Claude Code.

Architecture (v2.0 - Async with Task Polling)
---------------------------------------------
Write operations (checkpoint/knowledge saves) are now async:

1. Tool receives request
2. Tool validates input (fast, sync)
3. Tool queues Task and returns "📋 Queued" + POLL instructions immediately
4. Claude spawns background Task subagent to poll using Read tool
5. Worker processes Task in background via asyncio.to_thread()
6. Worker writes result to ~/.sage/tasks/<task_id>.result
7. Worker touches ~/.sage/tasks/<task_id>.done (signals completion)
8. Task subagent detects .done file via Read, returns result
9. Claude Code shows native <task-notification> automatically

This approach gives native subagent-like UX with no bash permissions needed.

Read operations remain synchronous (Claude needs the result immediately).

Usage:
    python -m sage.mcp_server

Or via Claude Code MCP config:
    {
        "mcpServers": {
            "sage": {
                "command": "python",
                "args": ["-m", "sage.mcp_server"]
            }
        }
    }
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from sage.config import detect_project_root, get_sage_config
from sage.logging import (
    get_logger,
    log_task_completed,
    log_task_failed,
    log_task_queued,
    log_task_started,
)
from sage.tasks import (
    Task,
    TaskResult,
    clear_pending_tasks,
    generate_task_id,
    get_task_paths,
    load_pending_tasks,
    save_pending_tasks,
    validate_task_data,
    write_task_result,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)
from sage.checkpoint import (
    Checkpoint,
    create_checkpoint_from_dict,
    format_checkpoint_for_context,
    is_duplicate_checkpoint,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)
from sage.knowledge import (
    add_knowledge,
    format_recalled_context,
    get_pending_todos,
    list_knowledge,
    list_todos,
    mark_todo_done,
    recall_knowledge,
    remove_knowledge,
)


def _format_poll_instructions(task_id: str) -> str:
    """Format polling instructions for Claude to track async task completion.

    Uses a background Task agent to poll for completion and return results.
    Agent type and model are configurable via SageConfig (poll_agent_type, poll_agent_model).

    Use `sage_reload_config` to pick up changes without restarting Claude Code.
    """
    config = get_sage_config(_PROJECT_ROOT)
    paths = get_task_paths(task_id)
    prompt = f"""Poll for Sage async task completion:

1. Read file: {paths["done_file"]}
2. If "file not found" error, run: Bash(sleep 2), then goto step 1
3. Once file exists, Read: {paths["result_file"]}
4. Parse JSON, return the "message" field value

Max 30 attempts. If timeout, return "Sage: task timed out after 60s"."""

    agent_type = config.poll_agent_type
    model = config.poll_agent_model
    return f"POLL: Task(subagent_type='{agent_type}', model='{model}', run_in_background=true, prompt=below)\n```\n{prompt}\n```"


# Initialize MCP server
mcp = FastMCP("sage")

# Detect project root at startup for project-local checkpoints
_PROJECT_ROOT = detect_project_root()

# =============================================================================
# Async Infrastructure
# =============================================================================

# Task queue for background processing
_task_queue: asyncio.Queue[Task] = asyncio.Queue()

# Worker task handle (for shutdown)
_worker_task: asyncio.Task | None = None

# Shutdown flag
_shutdown_requested: bool = False


async def _worker() -> None:
    """Background worker that processes tasks from queue.

    Runs continuously until shutdown is requested.
    Processes tasks via asyncio.to_thread() to avoid blocking.
    """
    global _shutdown_requested
    import time

    while not _shutdown_requested:
        try:
            # Wait for task with timeout to check shutdown flag periodically
            try:
                task = await asyncio.wait_for(_task_queue.get(), timeout=1.0)
            except TimeoutError:
                continue

            # Log task started
            log_task_started(task.id, task.type)
            start_time = time.monotonic()

            # Process the task
            try:
                result = await _process_task(task)

                # Calculate duration
                duration_ms = int((time.monotonic() - start_time) * 1000)

                # Write task result file for Task polling to pick up
                write_task_result(
                    task_id=task.id,
                    status=result.status,
                    message=result.message,
                    error=result.error,
                )

                # Log completion
                if result.status == "success":
                    log_task_completed(task.id, task.type, duration_ms)
                else:
                    log_task_failed(task.id, task.type, result.error or "Unknown error")

            except Exception as e:
                # Unexpected error - write failure result
                duration_ms = int((time.monotonic() - start_time) * 1000)
                log_task_failed(task.id, task.type, str(e))
                write_task_result(
                    task_id=task.id,
                    status="failed",
                    message=f"Task failed: {e}",
                    error=str(e),
                )

            finally:
                _task_queue.task_done()

        except asyncio.CancelledError:
            break
        except Exception:
            # Don't let worker crash from unexpected errors
            logger.error("Worker encountered unexpected error", exc_info=True)


async def _process_task(task: Task) -> TaskResult:
    """Process a single task in a thread pool.

    Args:
        task: Task to process

    Returns:
        TaskResult with success/failure status
    """
    try:
        if task.type == "checkpoint":
            return await asyncio.to_thread(_sync_save_checkpoint, task)
        elif task.type == "knowledge":
            return await asyncio.to_thread(_sync_save_knowledge, task)
        else:
            return TaskResult(
                task_id=task.id,
                status="failed",
                message=f"Unknown task type: {task.type}",
                error=f"Invalid type: {task.type}",
            )
    except Exception as e:
        logger.exception(f"Task processing failed: {task.id}")
        return TaskResult(
            task_id=task.id,
            status="failed",
            message=f"Task failed: {e}",
            error=str(e),
        )


def _sync_save_checkpoint(task: Task) -> TaskResult:
    """Synchronous checkpoint save (runs in thread pool).

    Args:
        task: Checkpoint task with data

    Returns:
        TaskResult with success/failure status
    """
    try:
        data = task.data

        checkpoint = create_checkpoint_from_dict(
            data,
            trigger=data.get("trigger", "synthesis"),
            template=data.get("template", "default"),
        )

        # Add depth metadata if present
        if data.get("message_count") or data.get("token_estimate"):
            checkpoint = Checkpoint(
                id=checkpoint.id,
                ts=checkpoint.ts,
                trigger=checkpoint.trigger,
                core_question=checkpoint.core_question,
                thesis=checkpoint.thesis,
                confidence=checkpoint.confidence,
                open_questions=checkpoint.open_questions,
                sources=checkpoint.sources,
                tensions=checkpoint.tensions,
                unique_contributions=checkpoint.unique_contributions,
                key_evidence=checkpoint.key_evidence,
                reasoning_trace=checkpoint.reasoning_trace,
                action_goal=checkpoint.action_goal,
                action_type=checkpoint.action_type,
                skill=checkpoint.skill,
                project=checkpoint.project,
                parent_checkpoint=checkpoint.parent_checkpoint,
                message_count=data.get("message_count", 0),
                token_estimate=data.get("token_estimate", 0),
            )

        path = save_checkpoint(checkpoint, project_path=_PROJECT_ROOT)

        template = data.get("template", "default")
        template_info = f" (template: {template})" if template != "default" else ""

        return TaskResult(
            task_id=task.id,
            status="success",
            message=f"Checkpoint saved: {checkpoint.id}{template_info}",
        )

    except Exception as e:
        logger.exception(f"Checkpoint save failed: {task.id}")
        return TaskResult(
            task_id=task.id,
            status="failed",
            message=f"Checkpoint save failed: {e}",
            error=str(e),
        )


def _sync_save_knowledge(task: Task) -> TaskResult:
    """Synchronous knowledge save (runs in thread pool).

    Args:
        task: Knowledge task with data

    Returns:
        TaskResult with success/failure status
    """
    try:
        data = task.data

        item = add_knowledge(
            content=data["content"],
            knowledge_id=data["knowledge_id"],
            keywords=data["keywords"],
            skill=data.get("skill"),
            source=data.get("source", ""),
            item_type=data.get("item_type", "knowledge"),
        )

        scope = f"skill:{data.get('skill')}" if data.get("skill") else "global"
        type_label = f" [{item.item_type}]" if item.item_type != "knowledge" else ""

        return TaskResult(
            task_id=task.id,
            status="success",
            message=f"Knowledge saved: {item.id}{type_label} ({scope})",
        )

    except Exception as e:
        logger.exception(f"Knowledge save failed: {task.id}")
        return TaskResult(
            task_id=task.id,
            status="failed",
            message=f"Knowledge save failed: {e}",
            error=str(e),
        )


async def _warmup_model() -> None:
    """Pre-load embedding model in background.

    This prevents the 30+ second first-load delay from blocking MCP tools.
    """
    try:
        from sage import embeddings

        if embeddings.is_available():
            logger.info("Warming up embedding model...")
            await asyncio.to_thread(embeddings.get_model)
            logger.info("Embedding model warmed up")
    except Exception:
        # Warmup failure is not critical
        logger.warning("Embedding model warmup failed (will load on first use)")


async def _reload_pending_tasks() -> None:
    """Reload pending tasks from previous session."""
    tasks = load_pending_tasks()
    if tasks:
        logger.info(f"Reloading {len(tasks)} pending tasks from previous session")
        for task in tasks:
            await _task_queue.put(task)
        clear_pending_tasks()


# =============================================================================
# Lifecycle Management
# =============================================================================


def _ensure_worker_running() -> None:
    """Ensure the background worker is running.

    This is called lazily when a task needs to be queued.
    Uses module-level state to ensure single worker instance.
    """
    global _worker_task, _shutdown_requested

    if _worker_task is not None and not _worker_task.done():
        return  # Worker already running

    if _shutdown_requested:
        return  # Don't start if shutting down

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop - this shouldn't happen in async context
        logger.warning("No event loop - worker not started")
        return

    _worker_task = loop.create_task(_worker())
    logger.info("Sage async worker started")

    # Reload pending tasks on first start
    loop.create_task(_reload_pending_tasks())

    # Warm up model (fire and forget)
    loop.create_task(_warmup_model())


def _sync_shutdown() -> None:
    """Synchronous shutdown handler for atexit.

    Note: This runs in a sync context, so we can't await the queue.
    We just save any pending tasks for next session.
    """
    global _shutdown_requested

    _shutdown_requested = True

    # Save any remaining tasks synchronously
    pending = []
    while not _task_queue.empty():
        try:
            pending.append(_task_queue.get_nowait())
        except Exception:
            break

    if pending:
        save_pending_tasks(pending)
        logger.info(f"Saved {len(pending)} pending tasks for next session")


# Register shutdown handler
import atexit

atexit.register(_sync_shutdown)


# =============================================================================
# System Tools
# =============================================================================


@mcp.tool()
def sage_version() -> str:
    """Get Sage version and configuration info.

    Returns version number, embedding model, and key thresholds.
    Useful for debugging and ensuring you're on the expected version.
    """
    from sage import __version__
    from sage.config import get_sage_config
    from sage.embeddings import is_available as embeddings_available

    cfg = get_sage_config()

    lines = [
        f"Sage v{__version__}",
        "",
        "Configuration:",
        f"  Embedding model: {cfg.embedding_model}",
        f"  Embeddings available: {embeddings_available()}",
        f"  Recall threshold: {cfg.recall_threshold}",
        f"  Embedding weight: {cfg.embedding_weight}",
        f"  Keyword weight: {cfg.keyword_weight}",
    ]

    return "\n".join(lines)


@mcp.tool()
def sage_health() -> str:
    """Check Sage system health and diagnostics.

    Returns status of all Sage subsystems including:
    - Configuration files
    - Embedding model availability
    - Checkpoint and knowledge counts
    - File permissions
    - Pending tasks

    Use this to diagnose issues or verify Sage is properly configured.
    """
    from sage import __version__, check_for_updates
    from sage.checkpoint import CHECKPOINTS_DIR, list_checkpoints
    from sage.config import CONFIG_PATH, SAGE_DIR, get_sage_config
    from sage.embeddings import check_model_mismatch, get_configured_model, is_available
    from sage.knowledge import KNOWLEDGE_DIR, list_knowledge
    from sage.tasks import TASKS_DIR, load_pending_tasks

    lines = ["Sage Health Check", "─" * 40]
    issues = []

    # Check version
    update_available, latest = check_for_updates()
    if update_available and latest:
        lines.append(f"⚠️ Update available: v{__version__} → v{latest}")
        issues.append(f"Run: pip install --upgrade claude-sage")
    else:
        lines.append(f"✓ Version: v{__version__} (latest)")

    # Check .sage directory
    if SAGE_DIR.exists():
        lines.append(f"✓ Sage directory: {SAGE_DIR}")
    else:
        lines.append(f"✗ Sage directory missing: {SAGE_DIR}")
        issues.append("Run 'sage init' to create directory")

    # Check config
    config = get_sage_config()
    if CONFIG_PATH.exists():
        lines.append(f"✓ Config loaded: {CONFIG_PATH}")
    else:
        lines.append("! No config file (using defaults)")

    # Check embeddings
    if is_available():
        model_name = get_configured_model()
        mismatch, old_model, new_model = check_model_mismatch()
        if mismatch:
            lines.append(f"! Embeddings: model changed ({old_model} → {new_model})")
            issues.append("Run 'sage admin rebuild-embeddings' to update")
        else:
            lines.append(f"✓ Embeddings: {model_name}")
    else:
        lines.append("! Embeddings not available")
        issues.append("Install with: pip install claude-sage[embeddings]")

    # Check checkpoints
    if CHECKPOINTS_DIR.exists():
        checkpoints = list_checkpoints(project_path=_PROJECT_ROOT, limit=1000)
        cp_count = len(checkpoints)
        lines.append(f"✓ Checkpoints: {cp_count} saved")
    else:
        lines.append("○ Checkpoints directory: not created yet")

    # Check knowledge
    if KNOWLEDGE_DIR.exists():
        knowledge = list_knowledge()
        k_count = len(knowledge)
        lines.append(f"✓ Knowledge: {k_count} items")
    else:
        lines.append("○ Knowledge directory: not created yet")

    # Check pending tasks
    if TASKS_DIR.exists():
        pending = load_pending_tasks()
        if pending:
            lines.append(f"! Pending tasks: {len(pending)}")
            issues.append("Pending tasks will be processed on next MCP server start")
        else:
            lines.append("✓ Pending tasks: none")
    else:
        lines.append("○ Tasks directory: not created yet")

    # Summary
    lines.append("")
    if issues:
        lines.append(f"Found {len(issues)} issue(s):")
        for issue in issues:
            lines.append(f"  • {issue}")
    else:
        lines.append("All systems healthy!")

    return "\n".join(lines)


@mcp.tool()
def sage_get_config() -> str:
    """Get current Sage configuration values.

    Shows both runtime config and tuning parameters with their
    current values vs defaults.

    Returns:
        Formatted configuration display
    """
    from sage.config import SAGE_DIR, Config, SageConfig, get_sage_config

    lines = ["Sage Configuration", "─" * 40]

    # Runtime config
    cfg = Config.load()
    lines.append("")
    lines.append("Runtime (config.yaml):")
    lines.append(f"  model: {cfg.model}")
    lines.append(f"  max_history: {cfg.max_history}")
    lines.append(f"  cache_ttl: {cfg.cache_ttl}")
    lines.append(f"  api_key: {'***' if cfg.api_key else '(not set)'}")

    # Tuning config
    tuning = get_sage_config(_PROJECT_ROOT)
    defaults = SageConfig()

    lines.append("")
    lines.append("Tuning (tuning.yaml):")

    def show_value(key: str, current, default):
        marker = "" if current == default else " (modified)"
        lines.append(f"  {key}: {current}{marker}")

    show_value("embedding_model", tuning.embedding_model, defaults.embedding_model)
    show_value("recall_threshold", tuning.recall_threshold, defaults.recall_threshold)
    show_value("dedup_threshold", tuning.dedup_threshold, defaults.dedup_threshold)
    show_value("embedding_weight", tuning.embedding_weight, defaults.embedding_weight)
    show_value("keyword_weight", tuning.keyword_weight, defaults.keyword_weight)
    show_value("depth_min_messages", tuning.depth_min_messages, defaults.depth_min_messages)
    show_value("depth_min_tokens", tuning.depth_min_tokens, defaults.depth_min_tokens)

    # Show config file locations
    lines.append("")
    lines.append("Config locations:")
    lines.append(f"  User: {SAGE_DIR}")
    if _PROJECT_ROOT:
        lines.append(f"  Project: {_PROJECT_ROOT / '.sage'}")

    return "\n".join(lines)


@mcp.tool()
def sage_debug_query(query: str, skill: str = "", include_checkpoints: bool = True) -> str:
    """Debug what knowledge and checkpoints would match a query.

    Shows detailed scoring breakdown to understand why items were/weren't recalled.
    Use this to:
    - See why knowledge wasn't recalled (score vs threshold)
    - Verify checkpoint relevance before loading
    - Identify near-misses that might warrant threshold tuning

    Args:
        query: The query to test against knowledge and checkpoints
        skill: Optional skill context for knowledge scoping
        include_checkpoints: Whether to include checkpoint matches (default True)

    Returns:
        Detailed scoring breakdown with matches and near-misses
    """
    from sage import embeddings
    from sage.checkpoint import _get_checkpoint_embedding_store, list_checkpoints
    from sage.config import get_sage_config
    from sage.knowledge import (
        _get_all_embedding_similarities,
        load_index,
        score_item_combined,
        get_type_threshold,
    )

    cfg = get_sage_config()
    lines = [
        f"Debug Query: \"{query}\"",
        f"Skill: {skill or '(none)'}",
        f"Weights: embedding={cfg.embedding_weight:.0%}, keyword={cfg.keyword_weight:.0%}",
        "",
    ]

    # ─────────────────────────────────────────────────────────────────────────
    # Knowledge Scoring
    # ─────────────────────────────────────────────────────────────────────────
    lines.append("═══ Knowledge Matches ═══")

    items = load_index()
    if not items:
        lines.append("No knowledge items found.")
    else:
        # Get embedding similarities
        embedding_sims = {}
        if embeddings.is_available():
            embedding_sims = _get_all_embedding_similarities(query)

        # Score all items
        scored = []
        for item in items:
            sim = embedding_sims.get(item.id)
            score = score_item_combined(item, query, skill, sim)
            threshold = get_type_threshold(item.item_type)
            scored.append((item, score, sim, threshold))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        # Separate above/below threshold
        above = [(i, s, sim, t) for i, s, sim, t in scored if s >= t]
        near_miss = [(i, s, sim, t) for i, s, sim, t in scored if t - 2.0 <= s < t]

        if above:
            lines.append(f"Would recall ({len(above)} items):")
            for item, score, sim, threshold in above[:5]:  # Limit to 5
                sim_str = f"emb={sim:.2f}" if sim is not None else "emb=N/A"
                lines.append(f"  ✓ {item.id}")
                lines.append(f"    score={score:.2f} ({sim_str}) threshold={threshold:.1f} type={item.item_type}")
                lines.append(f"    keywords: {', '.join(item.triggers.keywords[:5])}")
        else:
            lines.append("No items above threshold.")

        if near_miss:
            lines.append("")
            lines.append(f"Near misses ({len(near_miss)} items within 2.0 of threshold):")
            for item, score, sim, threshold in near_miss[:3]:  # Limit to 3
                sim_str = f"emb={sim:.2f}" if sim is not None else "emb=N/A"
                gap = threshold - score
                lines.append(f"  ✗ {item.id}")
                lines.append(f"    score={score:.2f} ({sim_str}) threshold={threshold:.1f} gap={gap:.2f}")

            # Threshold suggestion
            highest_miss_score = max(s for _, s, _, _ in near_miss)
            suggested = (highest_miss_score / 10.0) - 0.01
            lines.append("")
            lines.append(f"Tip: Lower recall_threshold to {suggested:.2f} to include near-misses")

    # ─────────────────────────────────────────────────────────────────────────
    # Checkpoint Scoring
    # ─────────────────────────────────────────────────────────────────────────
    if include_checkpoints:
        lines.append("")
        lines.append("═══ Checkpoint Matches ═══")

        if not embeddings.is_available():
            lines.append("Embeddings not available for checkpoint search.")
        else:
            checkpoints = list_checkpoints(project_path=_PROJECT_ROOT, limit=50)
            if not checkpoints:
                lines.append("No checkpoints found.")
            else:
                result = embeddings.get_query_embedding(query)
                if result.is_err():
                    lines.append(f"Failed to embed query: {result.unwrap_err().message}")
                else:
                    query_emb = result.unwrap()
                    store = _get_checkpoint_embedding_store()

                    # Score checkpoints
                    scored = []
                    for cp in checkpoints:
                        cp_emb = store.get(cp.id)
                        if cp_emb is not None:
                            sim = float(embeddings.cosine_similarity(query_emb, cp_emb))
                            scored.append((cp, sim))

                    if not scored:
                        lines.append("No checkpoints with embeddings found.")
                    else:
                        scored.sort(key=lambda x: x[1], reverse=True)

                        matches = [(cp, sim) for cp, sim in scored if sim >= 0.5]
                        near_miss = [(cp, sim) for cp, sim in scored if 0.3 <= sim < 0.5]

                        if matches:
                            lines.append(f"Relevant ({len(matches)}):")
                            for cp, sim in matches[:5]:
                                lines.append(f"  ✓ {cp.id[:50]} (sim={sim:.2f})")
                                lines.append(f"    {cp.thesis[:70]}...")
                        else:
                            lines.append("No highly relevant checkpoints (similarity < 0.5)")

                        if near_miss:
                            lines.append("")
                            lines.append(f"Potentially related ({len(near_miss)}):")
                            for cp, sim in near_miss[:3]:
                                lines.append(f"  ~ {cp.id[:50]} (sim={sim:.2f})")

    return "\n".join(lines)


# =============================================================================
# Checkpoint Tools
# =============================================================================


@mcp.tool()
async def sage_save_checkpoint(
    core_question: str,
    thesis: str,
    confidence: float,
    trigger: str = "synthesis",
    open_questions: list[str] | None = None,
    sources: list[dict] | None = None,
    tensions: list[dict] | None = None,
    unique_contributions: list[dict] | None = None,
    action_goal: str = "",
    action_type: str = "",
    key_evidence: list[str] | None = None,
    reasoning_trace: str = "",
    template: str = "default",
) -> str:
    """Save a semantic checkpoint of the current research state.

    Creates a checkpoint capturing the research synthesis, sources, tensions,
    and unique discoveries. Use this when detecting synthesis moments, branch
    points, hypothesis validation, or when explicitly asked.

    Args:
        core_question: What decision/action is this research driving toward?
        thesis: Current synthesized position (1-2 sentences)
        confidence: Confidence in thesis (0.0-1.0)
        trigger: What triggered (synthesis, branch_point, constraint, transition, manual)
        open_questions: What's still unknown or needs more research
        sources: List of sources with {id, type, take, relation}
        tensions: List of source disagreements with {between: [src1, src2], nature, resolution}
        unique_contributions: Your discoveries with {type, content}
        action_goal: What's being done with this research
        action_type: Type of action (decision, implementation, learning, exploration)
        key_evidence: Concrete facts/data points supporting the thesis (for context hydration)
        reasoning_trace: Narrative explaining the thinking process that led to conclusions
        template: Checkpoint template to use (default, research, decision, code-review)

    Returns:
        Confirmation message with checkpoint ID (queued for async save)
    """
    # Validate confidence bounds (fast, sync)
    if not (0.0 <= confidence <= 1.0):
        return f"⏸ Invalid confidence {confidence}: must be between 0.0 and 1.0"

    # Build task data
    data = {
        "core_question": core_question,
        "thesis": thesis,
        "confidence": confidence,
        "open_questions": open_questions or [],
        "sources": sources or [],
        "tensions": tensions or [],
        "unique_contributions": unique_contributions or [],
        "action": {"goal": action_goal, "type": action_type},
        "key_evidence": key_evidence or [],
        "reasoning_trace": reasoning_trace,
        "trigger": trigger,
        "template": template,
    }

    # Validate task data
    is_valid, error_msg = validate_task_data("checkpoint", data)
    if not is_valid:
        return f"⏸ Invalid checkpoint data: {error_msg}"

    # Check if async is enabled
    config = get_sage_config(_PROJECT_ROOT)

    if config.async_enabled:
        # Ensure worker is running
        _ensure_worker_running()

        # Queue for async processing
        task = Task(
            id=generate_task_id(),
            type="checkpoint",
            data=data,
        )
        await _task_queue.put(task)
        log_task_queued(task.id, task.type)

        thesis_preview = thesis[:50] + "..." if len(thesis) > 50 else thesis
        thesis_preview = thesis_preview.replace("\n", " ")
        template_info = f" (template: {template})" if template != "default" else ""

        poll_instructions = _format_poll_instructions(task.id)
        return (
            f"📋 Checkpoint queued{template_info}: {thesis_preview}\n"
            f"Task: {task.id}\n\n"
            f"{poll_instructions}"
        )
    else:
        # Sync fallback
        checkpoint = create_checkpoint_from_dict(data, trigger=trigger, template=template)
        path = save_checkpoint(checkpoint, project_path=_PROJECT_ROOT)

        template_info = f" (template: {template})" if template != "default" else ""
        return f"✓ Checkpoint saved: {checkpoint.id}{template_info}\nPath: {path}"


@mcp.tool()
def sage_list_checkpoints(limit: int = 10, skill: str | None = None) -> str:
    """List saved research checkpoints.

    Args:
        limit: Maximum number of checkpoints to return
        skill: Optional skill filter

    Returns:
        Formatted list of checkpoints with ID, thesis, confidence, and date
    """
    checkpoints = list_checkpoints(project_path=_PROJECT_ROOT, skill=skill, limit=limit)

    if not checkpoints:
        return "No checkpoints found."

    lines = [f"Found {len(checkpoints)} checkpoint(s):\n"]
    for cp in checkpoints:
        thesis_preview = cp.thesis[:60] + "..." if len(cp.thesis) > 60 else cp.thesis
        thesis_preview = thesis_preview.replace("\n", " ")
        lines.append(f"- **{cp.id}**")
        lines.append(f"  Thesis: {thesis_preview}")
        lines.append(f"  Confidence: {cp.confidence:.0%} | Trigger: {cp.trigger}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def sage_load_checkpoint(checkpoint_id: str) -> str:
    """Load a checkpoint for context injection.

    Retrieves a checkpoint by ID (supports partial matching) and formats it
    for injection into the conversation context.

    Args:
        checkpoint_id: Full or partial checkpoint ID

    Returns:
        Formatted checkpoint context ready for injection
    """
    checkpoint = load_checkpoint(checkpoint_id, project_path=_PROJECT_ROOT)

    if not checkpoint:
        return f"Checkpoint not found: {checkpoint_id}"

    return format_checkpoint_for_context(checkpoint)


@mcp.tool()
def sage_search_checkpoints(query: str, limit: int = 5) -> str:
    """Search checkpoints by semantic similarity to a query.

    Finds checkpoints whose thesis is semantically similar to your query.
    Use this to find relevant past research before starting a new task.

    Args:
        query: What you're looking for (e.g., "JWT authentication patterns")
        limit: Maximum results to return (default 5)

    Returns:
        Ranked list of relevant checkpoints with similarity scores
    """
    from sage import embeddings
    from sage.checkpoint import _get_checkpoint_embedding_store

    if not embeddings.is_available():
        return (
            "Semantic search unavailable (embeddings not installed).\n"
            "Install with: pip install claude-sage[embeddings]"
        )

    # Get query embedding (with prefix for BGE models)
    result = embeddings.get_query_embedding(query)
    if result.is_err():
        return f"Failed to embed query: {result.unwrap_err().message}"

    query_embedding = result.unwrap()

    # Load checkpoints and their embeddings
    checkpoints = list_checkpoints(project_path=_PROJECT_ROOT, limit=50)
    if not checkpoints:
        return "No checkpoints found."

    store = _get_checkpoint_embedding_store()
    if len(store) == 0:
        return "No checkpoint embeddings found. Save some checkpoints first."

    # Score and rank
    scored = []
    for cp in checkpoints:
        cp_embedding = store.get(cp.id)
        if cp_embedding is None:
            continue
        similarity = float(embeddings.cosine_similarity(query_embedding, cp_embedding))
        scored.append((similarity, cp))

    if not scored:
        return "No checkpoints with embeddings found."

    # Sort by similarity descending
    scored.sort(key=lambda x: x[0], reverse=True)
    top_results = scored[:limit]

    # Format output
    lines = [f"Found {len(scored)} checkpoints. Top {len(top_results)} matches:\n"]
    for i, (similarity, cp) in enumerate(top_results, 1):
        thesis_preview = cp.thesis[:70] + "..." if len(cp.thesis) > 70 else cp.thesis
        thesis_preview = thesis_preview.replace("\n", " ")
        lines.append(f"{i}. **[{similarity:.0%}]** {cp.id}")
        lines.append(f"   {thesis_preview}")
        lines.append(f"   _Confidence: {cp.confidence:.0%} | {cp.trigger}_")
        lines.append("")

    lines.append("Use `sage_load_checkpoint(id)` to inject a checkpoint into context.")

    return "\n".join(lines)


# =============================================================================
# Knowledge Tools
# =============================================================================


@mcp.tool()
async def sage_save_knowledge(
    knowledge_id: str,
    content: str,
    keywords: list[str],
    skill: str | None = None,
    source: str = "",
    item_type: str = "knowledge",
) -> str:
    """Save an insight to the knowledge base for future recall.

    Knowledge items are automatically recalled when queries match their keywords.
    Keep items concise (~100 tokens) for efficient recall.

    Args:
        knowledge_id: Unique identifier (use kebab-case, e.g., "usdc-compliance")
        content: The knowledge content (markdown, keep concise)
        keywords: Trigger keywords for matching
        skill: Optional skill scope (None = global)
        source: Where this knowledge came from
        item_type: Type of knowledge (knowledge, preference, todo, reference)

    Returns:
        Confirmation message (queued for async save)
    """
    # Build task data
    data = {
        "knowledge_id": knowledge_id,
        "content": content,
        "keywords": keywords,
        "skill": skill,
        "source": source,
        "item_type": item_type,
    }

    # Validate task data
    is_valid, error_msg = validate_task_data("knowledge", data)
    if not is_valid:
        return f"⏸ Invalid knowledge data: {error_msg}"

    # Check if async is enabled
    config = get_sage_config(_PROJECT_ROOT)

    if config.async_enabled:
        # Ensure worker is running
        _ensure_worker_running()

        # Queue for async processing
        task = Task(
            id=generate_task_id(),
            type="knowledge",
            data=data,
        )
        await _task_queue.put(task)
        log_task_queued(task.id, task.type)

        scope = f"skill:{skill}" if skill else "global"
        type_label = f" [{item_type}]" if item_type != "knowledge" else ""

        poll_instructions = _format_poll_instructions(task.id)
        return (
            f"📋 Knowledge queued: {knowledge_id}{type_label} ({scope})\n"
            f"Task: {task.id}\n\n"
            f"{poll_instructions}"
        )
    else:
        # Sync fallback
        item = add_knowledge(
            content=content,
            knowledge_id=knowledge_id,
            keywords=keywords,
            skill=skill,
            source=source,
            item_type=item_type,
        )

        scope = f"skill:{skill}" if skill else "global"
        type_label = f" [{item.item_type}]" if item.item_type != "knowledge" else ""
        return f"✓ Knowledge saved: {item.id}{type_label} ({scope}, ~{item.metadata.tokens} tokens)"


@mcp.tool()
def sage_recall_knowledge(query: str, skill: str = "") -> str:
    """Recall relevant knowledge for a query.

    Searches the knowledge base for items matching the query and returns
    formatted context for injection.

    Args:
        query: The query to match against
        skill: Current skill context (for scoped knowledge)

    Returns:
        Formatted recalled knowledge or message if none found
    """
    from sage import embeddings

    result = recall_knowledge(query, skill)

    if result.count == 0:
        if not embeddings.is_available():
            return "No relevant knowledge found.\n\n💡 *Tip: `pip install claude-sage[embeddings]` for semantic recall*"
        return "No relevant knowledge found."

    return format_recalled_context(result)


@mcp.tool()
def sage_list_knowledge(skill: str | None = None) -> str:
    """List stored knowledge items.

    Args:
        skill: Optional skill filter

    Returns:
        List of knowledge items with IDs and keywords
    """
    items = list_knowledge(skill)

    if not items:
        return "No knowledge items found."

    lines = [f"Found {len(items)} knowledge item(s):\n"]
    for item in items:
        scope = f"skill:{','.join(item.scope.skills)}" if item.scope.skills else "global"
        keywords = ", ".join(item.triggers.keywords[:5])
        if len(item.triggers.keywords) > 5:
            keywords += f" (+{len(item.triggers.keywords) - 5} more)"
        type_label = f" [{item.item_type}]" if item.item_type != "knowledge" else ""
        status_label = f" ({item.metadata.status})" if item.item_type == "todo" else ""
        lines.append(f"- **{item.id}**{type_label}{status_label} ({scope})")
        lines.append(f"  Keywords: {keywords}")
        lines.append(f"  Tokens: ~{item.metadata.tokens}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def sage_remove_knowledge(knowledge_id: str) -> str:
    """Remove a knowledge item.

    Args:
        knowledge_id: ID of the knowledge item to remove

    Returns:
        Confirmation or error message
    """
    if remove_knowledge(knowledge_id):
        return f"✓ Removed knowledge item: {knowledge_id}"
    return f"Knowledge item not found: {knowledge_id}"


@mcp.tool()
def sage_update_knowledge(
    knowledge_id: str,
    content: str | None = None,
    keywords: list[str] | None = None,
    status: str | None = None,
    source: str | None = None,
) -> str:
    """Update an existing knowledge item.

    Only provided fields are updated; others remain unchanged.
    Re-embeds automatically if content changes.

    Args:
        knowledge_id: ID of item to update
        content: New content (if changing)
        keywords: New keywords list (if changing)
        status: New status - 'active', 'deprecated', or 'archived' (if changing)
        source: New source attribution (if changing)

    Returns:
        Confirmation message or error

    Security:
        - knowledge_id is sanitized to prevent path traversal
        - Content is validated before storage
    """
    from sage.knowledge import update_knowledge

    # Validate at least one field provided
    if content is None and keywords is None and status is None and source is None:
        return "Error: Provide at least one field to update (content, keywords, status, or source)"

    # Validate status if provided
    if status is not None and status not in ("active", "deprecated", "archived"):
        return f"Error: Invalid status '{status}'. Valid values: active, deprecated, archived"

    result = update_knowledge(
        knowledge_id=knowledge_id,
        content=content,
        keywords=keywords,
        status=status,
        source=source,
    )

    if result is None:
        return f"Knowledge item not found: {knowledge_id}"

    updates = []
    if content is not None:
        updates.append(f"content ({len(content)} chars)")
    if keywords is not None:
        updates.append(f"keywords ({len(keywords)} items)")
    if status is not None:
        updates.append(f"status={status}")
    if source is not None:
        updates.append(f"source")

    return f"✓ Updated {knowledge_id}: {', '.join(updates)}"


@mcp.tool()
def sage_deprecate_knowledge(
    knowledge_id: str,
    reason: str,
    replacement_id: str | None = None,
) -> str:
    """Mark a knowledge item as deprecated.

    Deprecated items still appear in search but show a warning.
    Use for outdated information you want to flag but not delete.

    Args:
        knowledge_id: ID of item to deprecate
        reason: Why this is deprecated (required)
        replacement_id: Optional ID of replacement item

    Returns:
        Confirmation message or error

    Security:
        - IDs are sanitized to prevent injection
    """
    from sage.knowledge import deprecate_knowledge

    if not reason or not reason.strip():
        return "Error: reason is required"

    result = deprecate_knowledge(
        knowledge_id=knowledge_id,
        reason=reason.strip(),
        replacement_id=replacement_id,
    )

    if result is None:
        return f"Knowledge item not found: {knowledge_id}"

    msg = f"⚠️ Deprecated: {knowledge_id}\nReason: {reason}"
    if replacement_id:
        msg += f"\nReplacement: {replacement_id}"
    return msg


@mcp.tool()
def sage_archive_knowledge(knowledge_id: str) -> str:
    """Archive a knowledge item (hide from recall).

    Archived items are preserved but excluded from retrieval.
    Use for obsolete items you want to keep for reference.

    To restore: sage_update_knowledge(id, status='active')

    Args:
        knowledge_id: ID of item to archive

    Returns:
        Confirmation message or error

    Security:
        - ID is sanitized to prevent path traversal
    """
    from sage.knowledge import archive_knowledge

    result = archive_knowledge(knowledge_id)

    if result is None:
        return f"Knowledge item not found: {knowledge_id}"

    return f"📦 Archived: {knowledge_id}\nRestore with: sage_update_knowledge('{knowledge_id}', status='active')"


# =============================================================================
# Todo Tools
# =============================================================================


@mcp.tool()
def sage_list_todos(status: str = "") -> str:
    """List todo items.

    Args:
        status: Filter by status (pending, done) or empty for all

    Returns:
        Formatted list of todos
    """
    status_filter = status if status else None
    todos = list_todos(status=status_filter)

    if not todos:
        return "No todos found."

    lines = [f"Found {len(todos)} todo(s):\n"]
    for todo in todos:
        status_icon = "☐" if todo.metadata.status == "pending" else "☑"
        keywords = ", ".join(todo.triggers.keywords[:3])
        lines.append(f"{status_icon} **{todo.id}** ({todo.metadata.status})")
        if keywords:
            lines.append(f"   Keywords: {keywords}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def sage_mark_todo_done(todo_id: str) -> str:
    """Mark a todo as done.

    Args:
        todo_id: ID of the todo to mark as done

    Returns:
        Confirmation or error message
    """
    if mark_todo_done(todo_id):
        return f"✓ Marked todo as done: {todo_id}"
    return f"Todo not found: {todo_id}"


@mcp.tool()
def sage_get_pending_todos() -> str:
    """Get pending todos for session-start injection.

    Returns:
        Formatted list of pending todos or message if none
    """
    todos = get_pending_todos()

    if not todos:
        return "No pending todos."

    lines = ["📋 **Pending Todos:**\n"]
    for todo in todos:
        lines.append(f"- **{todo.id}**: {todo.content[:100] if todo.content else '(no content)'}")
    lines.append("")
    lines.append("_Use `sage_mark_todo_done(id)` when completed._")

    return "\n".join(lines)


# =============================================================================
# Admin Tools
# =============================================================================


@mcp.tool()
def sage_set_config(key: str, value: str, project_level: bool = False) -> str:
    """Set a Sage tuning configuration value.

    Allows tuning thresholds based on debug output. Use with sage_debug_query
    to see near-misses, then adjust thresholds to include/exclude items.

    After setting, call sage_reload_config() to apply changes.

    Args:
        key: Config key (recall_threshold, embedding_weight, keyword_weight, etc.)
        value: New value (will be type-coerced based on field type)
        project_level: If True, saves to project .sage/tuning.yaml instead of user-level

    Returns:
        Confirmation message

    Example workflow:
        1. sage_debug_query("my topic") → see near-misses at score 2.8
        2. sage_set_config("recall_threshold", "0.25") → lower threshold
        3. sage_reload_config() → apply changes
        4. sage_debug_query("my topic") → verify items now included
    """
    from pathlib import Path

    from sage.config import SAGE_DIR, SageConfig, get_sage_config

    # Determine location
    if project_level:
        sage_dir = _PROJECT_ROOT / ".sage" if _PROJECT_ROOT else Path.cwd() / ".sage"
    else:
        sage_dir = SAGE_DIR

    # Get valid tuning keys
    tuning_keys = {f.name for f in SageConfig.__dataclass_fields__.values()}

    # Normalize key (allow hyphens)
    key = key.replace("-", "_")

    if key not in tuning_keys:
        valid_keys = ", ".join(sorted(tuning_keys))
        return f"Unknown config key: {key}\n\nValid tuning keys: {valid_keys}"

    # Load current config
    tuning = get_sage_config(_PROJECT_ROOT) if not project_level else SageConfig.load(sage_dir)

    # Type coercion based on field type
    field_type = SageConfig.__dataclass_fields__[key].type
    try:
        if field_type == float:
            typed_value = float(value)
        elif field_type == int:
            typed_value = int(value)
        else:
            typed_value = value
    except ValueError:
        return f"Invalid value '{value}' for {key} (expected {field_type.__name__})"

    # Create new config with updated value
    current_dict = tuning.to_dict()
    current_dict[key] = typed_value
    new_tuning = SageConfig(**current_dict)

    # Ensure directory exists
    sage_dir.mkdir(parents=True, exist_ok=True)

    # Save
    new_tuning.save(sage_dir)

    location = "project" if project_level else "user"
    return f"✓ Set {key} = {typed_value} ({location}-level)\n\nCall sage_reload_config() to apply."


@mcp.tool()
def sage_reload_config() -> str:
    """Reload Sage configuration and clear cached models.

    Call this after changing Sage config (e.g., embedding_model) to pick up
    changes without restarting Claude Code. Clears the cached embedding model
    so the next operation loads the newly configured model.

    Returns:
        Status message showing what was reloaded
    """
    global _PROJECT_ROOT

    from sage import embeddings
    from sage.config import detect_project_root, get_sage_config

    # Re-detect project root
    old_project = _PROJECT_ROOT
    _PROJECT_ROOT = detect_project_root()
    project_changed = old_project != _PROJECT_ROOT

    # Clear embedding model cache
    old_model = embeddings._model_name
    embeddings.clear_model_cache()

    # Get new config to show what's active
    config = get_sage_config(_PROJECT_ROOT)

    lines = ["✓ Configuration reloaded\n"]

    if project_changed:
        lines.append(f"  Project root: {old_project} -> {_PROJECT_ROOT}")
    else:
        lines.append(f"  Project root: {_PROJECT_ROOT or '(none)'}")

    if old_model:
        lines.append(f"  Cleared cached model: {old_model}")
        lines.append(f"  New model (on next use): {config.embedding_model}")
    else:
        lines.append(f"  Embedding model: {config.embedding_model}")

    lines.append(f"  Recall threshold: {config.recall_threshold}")
    lines.append(f"  Dedup threshold: {config.dedup_threshold}")
    lines.append(f"  Poll agent: {config.poll_agent_type} ({config.poll_agent_model})")

    return "\n".join(lines)


# =============================================================================
# Autosave Tools
# =============================================================================

# Minimum confidence thresholds for each trigger type
AUTOSAVE_THRESHOLDS = {
    "research_start": 0.0,  # Always save starting point
    "web_search_complete": 0.3,  # Save if we learned something
    "synthesis": 0.5,  # Save meaningful conclusions
    "topic_shift": 0.3,  # Save before switching
    "user_validated": 0.4,  # User confirmed something
    "constraint_discovered": 0.3,  # Important pivot point
    "branch_point": 0.4,  # Decision point
    "precompact": 0.0,  # Always save before context compaction
    "context_threshold": 0.0,  # Always save when context threshold hit
    "manual": 0.0,  # Always save manual requests
}


@mcp.tool()
async def sage_autosave_check(
    trigger_event: str,
    core_question: str,
    current_thesis: str,
    confidence: float,
    open_questions: list[str] | None = None,
    sources: list[dict] | None = None,
    tensions: list[dict] | None = None,
    unique_contributions: list[dict] | None = None,
    key_evidence: list[str] | None = None,
    reasoning_trace: str = "",
    message_count: int = 0,
    token_estimate: int = 0,
) -> str:
    """Check if an autosave checkpoint should be created.

    Call this at natural breakpoints in research: after web searches, when reaching
    conclusions, when topics shift, etc. The tool decides whether to save based on
    the trigger type and confidence level.

    Args:
        trigger_event: What triggered this check (research_start, web_search_complete,
                      synthesis, topic_shift, user_validated, constraint_discovered,
                      branch_point, precompact, context_threshold, manual)
        core_question: What decision/action is this research driving toward?
        current_thesis: Current synthesized position (1-2 sentences)
        confidence: Confidence in thesis (0.0-1.0)
        open_questions: What's still unknown (optional)
        sources: Sources with {id, type, take, relation} (optional)
        tensions: Disagreements with {between, nature, resolution} (optional)
        unique_contributions: Discoveries with {type, content} (optional)
        key_evidence: Concrete facts/data points supporting the thesis (optional)
        reasoning_trace: Narrative explaining the thinking process (optional)
        message_count: Number of messages in conversation (for depth threshold)
        token_estimate: Estimated tokens used (for depth threshold)

    Returns:
        Confirmation if saved/queued, or explanation if not saved
    """
    config = get_sage_config(_PROJECT_ROOT)

    # Validate confidence bounds
    if not (0.0 <= confidence <= 1.0):
        return f"⏸ Invalid confidence {confidence}: must be between 0.0 and 1.0"

    # Validate trigger event
    threshold = AUTOSAVE_THRESHOLDS.get(trigger_event)
    if threshold is None:
        valid_triggers = ", ".join(AUTOSAVE_THRESHOLDS.keys())
        return f"Unknown trigger: {trigger_event}. Valid triggers: {valid_triggers}"

    # Check if we should save
    if confidence < threshold:
        return (
            f"⏸ Not saving (confidence {confidence:.0%} < {threshold:.0%} threshold "
            f"for {trigger_event}). Continue research to build confidence."
        )

    # Check for meaningful content
    if not current_thesis or len(current_thesis.strip()) < 10:
        return "⏸ Not saving: thesis too brief. Develop your position first."

    if not core_question or len(core_question.strip()) < 5:
        return "⏸ Not saving: no clear research question. What are we trying to answer?"

    # Depth threshold check - prevent shallow/noisy checkpoints
    # Skip depth check for manual, precompact, and context_threshold triggers
    exempt_triggers = {"manual", "precompact", "context_threshold", "research_start"}
    if trigger_event not in exempt_triggers:
        if message_count > 0 and message_count < config.depth_min_messages:
            return (
                f"⏸ Not saving: conversation too shallow ({message_count} messages, "
                f"need {config.depth_min_messages}). Continue research to build depth."
            )
        if token_estimate > 0 and token_estimate < config.depth_min_tokens:
            return (
                f"⏸ Not saving: conversation too shallow ({token_estimate} tokens, "
                f"need {config.depth_min_tokens}). Continue research to build depth."
            )

    # Check for duplicate (semantic similarity to recent checkpoints)
    # This check runs sync since it's fast (just embedding comparison)
    dedup_result = is_duplicate_checkpoint(current_thesis, project_path=_PROJECT_ROOT)
    if dedup_result.is_duplicate:
        return (
            f"⏸ Not saving: semantically similar to recent checkpoint "
            f"({dedup_result.similarity_score:.0%} similarity).\n"
            f"Similar: {dedup_result.similar_checkpoint_id}"
        )

    # Build checkpoint data
    data = {
        "core_question": core_question,
        "thesis": current_thesis,
        "confidence": confidence,
        "open_questions": open_questions or [],
        "sources": sources or [],
        "tensions": tensions or [],
        "unique_contributions": unique_contributions or [],
        "action": {"goal": "", "type": "learning"},
        "key_evidence": key_evidence or [],
        "reasoning_trace": reasoning_trace,
        "trigger": trigger_event,
        "template": "default",
        "message_count": message_count,
        "token_estimate": token_estimate,
    }

    thesis_preview = current_thesis[:50] + "..." if len(current_thesis) > 50 else current_thesis
    thesis_preview = thesis_preview.replace("\n", " ")

    if config.async_enabled:
        # Ensure worker is running
        _ensure_worker_running()

        # Queue for async processing
        task = Task(
            id=generate_task_id(),
            type="checkpoint",
            data=data,
        )
        await _task_queue.put(task)
        log_task_queued(task.id, task.type)

        poll_instructions = _format_poll_instructions(task.id)
        return (
            f"📋 Autosave queued: {thesis_preview}\n" f"Task: {task.id}\n\n" f"{poll_instructions}"
        )
    else:
        # Sync fallback
        checkpoint = create_checkpoint_from_dict(data, trigger=trigger_event)

        # Add depth metadata to checkpoint
        checkpoint = Checkpoint(
            id=checkpoint.id,
            ts=checkpoint.ts,
            trigger=checkpoint.trigger,
            core_question=checkpoint.core_question,
            thesis=checkpoint.thesis,
            confidence=checkpoint.confidence,
            open_questions=checkpoint.open_questions,
            sources=checkpoint.sources,
            tensions=checkpoint.tensions,
            unique_contributions=checkpoint.unique_contributions,
            key_evidence=checkpoint.key_evidence,
            reasoning_trace=checkpoint.reasoning_trace,
            action_goal=checkpoint.action_goal,
            action_type=checkpoint.action_type,
            skill=checkpoint.skill,
            project=checkpoint.project,
            parent_checkpoint=checkpoint.parent_checkpoint,
            message_count=message_count,
            token_estimate=token_estimate,
        )

        save_checkpoint(checkpoint, project_path=_PROJECT_ROOT)

        return f"📍 Autosaved: {thesis_preview}\nCheckpoint: {checkpoint.id}"


# =============================================================================
# Entry Point
# =============================================================================


def _check_for_updates_on_startup() -> None:
    """Check for updates and log if available."""
    from sage import __version__, check_for_updates

    try:
        update_available, latest = check_for_updates()
        if update_available and latest:
            logger.warning(
                f"Update available: v{__version__} → v{latest}. "
                f"Run: pip install --upgrade claude-sage"
            )
    except Exception:
        pass  # Never fail startup due to update check


def main():
    """Run the Sage MCP server."""
    _check_for_updates_on_startup()
    mcp.run()


if __name__ == "__main__":
    main()
