# Sage Async v2 Architecture

This document defines the architecture for making Sage non-blocking.

## Current State: Synchronous

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│  User   │────▶│  Claude │────▶│  Sage   │
└─────────┘     └─────────┘     └─────────┘
                    │               │
                    │  MCP call     │
                    │──────────────▶│
                    │               │ ⏳ 2-5 sec
                    │               │ (embedding + I/O)
                    │◀──────────────│
                    │  response     │
                    │               │
                    ▼
              (finally responds)
```

**Pain points:**
- 2-5 second checkpoint saves block Claude's response
- 30+ second first model load is brutal
- Hook-triggered checkpoints make this worse (user waiting for Claude AND Sage)

---

## Goal: Async/Non-blocking with Native Notifications

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│  User   │────▶│  Claude │────▶│  Sage   │
└─────────┘     └─────────┘     └─────────┘
                    │               │
                    │  MCP call     │
                    │──────────────▶│
                    │◀──────────────│ immediate "📋 Queued" + POLL instructions
                    │               │
                    │  spawn Task   │
                    │  subagent     │
                    │ (background)  │
                    ▼               │ ⏳ background work
              (responds fast)       │
                    │               ▼
                    │         ┌──────────┐
                    │         │  Worker  │
                    │         │ writes   │
                    │         │ .result  │
                    │         │ + .done  │
                    │         └──────────┘
                    │               │
                    ▼               ▼
              <task-notification>   (Task subagent detects .done via Read)
              ⏺ Sage: Checkpoint saved
```

**Key insight:** Claude Code's background Task tool gives us native subagent-like notifications. The subagent polls using the Read tool for file checks and Bash for sleep delays.

---

## Decisions (Locked In)

### What operations are async?

| Operation | Current Time | Async? | Rationale |
|-----------|--------------|--------|-----------|
| `sage_save_checkpoint` | 2-5 sec | ✅ Yes | Main pain point |
| `sage_autosave_check` | 2-5 sec | ✅ Yes | Same as above |
| `sage_save_knowledge` | 1-2 sec | ✅ Yes | Embedding gen |
| `sage_recall_knowledge` | 100-500ms | ❌ No | Claude needs the result |
| `sage_load_checkpoint` | 50ms | ❌ No | Fast, needs result |
| `sage_list_*` | 10ms | ❌ No | Fast, needs result |

**Decision:** Keep reads sync, make writes async.

### Queue architecture

**Decision:** `asyncio.Queue` with single FIFO worker.

- Simple, no dependencies
- Lost on crash is acceptable (checkpoints aren't critical)
- FIFO ordering is predictable

### Startup warmup

**Decision:** Background warmup on startup.

```python
async def on_startup():
    asyncio.create_task(warmup_model())  # Fire and forget

async def warmup_model():
    await asyncio.to_thread(embeddings.get_model)
```

Server starts fast, model loads in background.

---

## Notification Strategy: Task Polling (v2.0.1+)

### Research Finding: MCP Notifications Don't Work

**Claude Code does NOT support MCP push notifications** for custom servers.

Evidence (Jan 2026):
- `notifications/message` - Received but not displayed in UI
- `notifications/progress` - Not supported (Anthropic confirmed, GitHub #4157)
- `notifications/resources/updated` - Not supported (GitHub #7252)
- Feature requests closed as "not planned" (GitHub #1478, #1759)

Only `list_changed` notifications are supported (for tool/resource refresh).

### ~~Solution: Bash Watcher Pattern~~ (DEPRECATED - Security Risk)

The original v2.0 design used bash commands for polling. **This was abandoned due to security concerns:**

- Glob-based permission patterns (e.g., `Bash(*/track-task.sh *)`) can be exploited via social engineering
- Attacker creates malicious script at matching path, tricks Claude into running it
- No amount of task ID validation in the script prevents the malicious script itself from running

### Solution: Task Polling with Read Tool (v2.0.1+)

Use Claude's Task tool to spawn a background subagent that polls using Read (file check) and Bash (sleep delays). Uses `general-purpose` agent with `haiku` model for efficiency.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MCP Server                                      │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  MCP Tools   │───▶│  Task Queue  │───▶│   Worker     │                   │
│  │  (returns    │    │  (asyncio)   │    │  (asyncio)   │                   │
│  │   POLL inst) │    └──────────────┘    └──────────────┘                   │
│  └──────────────┘                               │                            │
│         │                                       ▼                            │
│         │                              ┌──────────────┐                      │
│         │                              │  Embeddings  │                      │
│         │                              │  (thread)    │                      │
│         │                              └──────────────┘                      │
│         │                                       │                            │
│         │                                       ▼                            │
│         │                              ┌──────────────┐                      │
│         │                              │   File I/O   │                      │
│         │                              └──────────────┘                      │
│         │                                       │                            │
│         │                                       ▼                            │
│         │                              ┌──────────────┐                      │
│         │                              │ Task Result  │                      │
│         │                              │ Files:       │                      │
│         │                              │ • .result    │                      │
│         │                              │ • .done      │                      │
│         │                              └──────────────┘                      │
└─────────│───────────────────────────────────────│───────────────────────────┘
          │                                       │
          │                                       │
          ▼                                       ▼
    Claude Code                         ┌──────────────────┐
          │                             │  Task Subagent   │
          │  spawns background          │  (polls for      │
          │  Task subagent              │   .done via Read)│
          │─────────────────────────────│                  │
          │                             └────────┬─────────┘
          │                                      │
          ▼                                      ▼
    <task-notification>              ⏺ Sage: Checkpoint saved
    (native Claude Code UX)          (output from subagent)
```

### How It Works

1. Tool queues task and returns immediately with POLL instructions:
   ```
   📋 Checkpoint queued: JWT is best for...
   Task: task_20260121_143052_a1b2c3d4

   POLL: Task(subagent_type='general-purpose', model='haiku', run_in_background=true, prompt=below)
   ```
   Poll for Sage async task completion:

   1. Read file: ~/.sage/tasks/task_20260121_143052_a1b2c3d4.done
   2. If "file not found" error, run: Bash(sleep 2), then goto step 1
   3. Once file exists, Read: ~/.sage/tasks/task_20260121_143052_a1b2c3d4.result
   4. Parse JSON, return the "message" field value
   ```

2. Claude spawns background Task subagent with the prompt

3. Worker processes task, writes files:
   - `~/.sage/tasks/<task_id>.result` - JSON with status, message
   - `~/.sage/tasks/<task_id>.done` - Empty marker file

4. Subagent detects `.done` via Read tool, returns result, Claude Code shows `<task-notification>`

### Task Result File Format

Worker writes to `~/.sage/tasks/<task_id>.result`:

```json
{
  "task_id": "task_20260121_143052_a1b2c3d4",
  "status": "success",
  "message": "Checkpoint saved: auth-patterns",
  "ts": "2026-01-21T14:30:55"
}
```

Then touches `~/.sage/tasks/<task_id>.done` to signal completion.

### Why Task Polling is More Secure

| Aspect | Bash Watcher (v2.0) | Task Polling (v2.0.1+) |
|--------|---------------------|------------------------|
| Permission needed | Bash glob pattern | Read + Bash sleep |
| Attack surface | Social engineering via path manipulation | Minimal (only sleep) |
| Auto-allow safe? | No (exploitable) | Yes (sleep is safe) |

### Why This Works

- Claude Code already tracks background Task subagents
- Task output appears as `<task-notification>`
- Same UX as native subagent notifications
- No Claude Code patches needed
- No bash permissions needed
- Tracking is optional (tasks complete regardless)

---

## Task Dataclass

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

@dataclass(frozen=True)
class Task:
    id: str
    type: Literal["checkpoint", "knowledge"]
    data: dict
    created: datetime

@dataclass
class TaskResult:
    task_id: str
    status: Literal["success", "failed"]
    message: str
    error: str | None = None
```

---

## Worker Implementation

```python
import asyncio
from pathlib import Path
import json

task_queue: asyncio.Queue[Task] = asyncio.Queue()
TASKS_DIR = Path.home() / ".sage" / "tasks"

async def worker():
    """Process tasks from queue, write result files."""
    while True:
        task = await task_queue.get()
        try:
            result = await process_task(task)
            write_task_result(task.id, result.status, result.message, result.error)
        except Exception as e:
            write_task_result(task.id, "failed", f"Task failed: {e}", str(e))
        finally:
            task_queue.task_done()

async def process_task(task: Task) -> TaskResult:
    """Process a single task."""
    if task.type == "checkpoint":
        return await asyncio.to_thread(save_checkpoint_sync, task.data)
    elif task.type == "knowledge":
        return await asyncio.to_thread(save_knowledge_sync, task.data)

def write_task_result(task_id: str, status: str, message: str, error: str = None):
    """Write result files for bash watcher to detect."""
    TASKS_DIR.mkdir(parents=True, exist_ok=True)

    result_file = TASKS_DIR / f"{task_id}.result"
    done_file = TASKS_DIR / f"{task_id}.done"

    # Write result as JSON
    with open(result_file, "w") as f:
        json.dump({
            "task_id": task_id,
            "status": status,
            "message": message,
            "error": error,
            "ts": datetime.now().isoformat()
        }, f)

    # Touch .done file to signal completion
    done_file.touch()
```

---

## Graceful Shutdown

When MCP server stops:

1. Stop accepting new tasks
2. Wait for queue to drain (with timeout)
3. Write any remaining tasks to `~/.sage/pending_tasks.jsonl`
4. On restart, reload pending tasks

```python
async def shutdown():
    # Wait up to 5 seconds for queue to drain
    try:
        await asyncio.wait_for(task_queue.join(), timeout=5.0)
    except asyncio.TimeoutError:
        # Save remaining tasks
        pending = []
        while not task_queue.empty():
            pending.append(task_queue.get_nowait())
        if pending:
            save_pending_tasks(pending)
```

---

## Implementation Status

### Phase 1: Infrastructure ✅
- [x] Add `Task` and `TaskResult` dataclasses
- [x] Add `asyncio.Queue` and worker loop
- [x] Add task result file writer
- [x] Background warmup on startup
- [x] Tests for queue behavior

### Phase 2: Async Checkpoints ✅
- [x] `sage_save_checkpoint` queues and returns immediately
- [x] `sage_autosave_check` queues and returns immediately
- [x] Worker processes checkpoint saves
- [x] Tests for async checkpoint flow

### Phase 3: Task Polling Notifications ✅
- [x] `get_task_paths()` returns paths for polling
- [x] Tools return POLL instructions in response
- [x] CLAUDE.md documents Task polling usage
- [x] Tests for task result files
- [x] Security audit: removed bash watcher (v2.0.1)

### Phase 4: Polish
- [x] Graceful shutdown with task persistence
- [ ] `sage admin tasks` to view recent task results (optional)
- [x] Logging/observability
- [x] Documentation

### Phase 5: Simplified Default (v2.1)
- [x] Changed `async_enabled` default to `false`
- [x] CLAUDE.md REQUIRED section for background Task usage
- [x] Sync operations + Task subagent = simpler architecture
- [x] Polling infrastructure retained as opt-in

---

## Architecture Decision: Sync + Task Subagent (v2.1)

After testing, we discovered a simpler approach:

**Instead of:** Sage handles async internally with queue + polling
**Use:** Claude Code's Task tool handles backgrounding natively

```
# Old approach (async_enabled=true)
Claude → Sage (queues, returns POLL) → Claude spawns poller → polls files → notification

# New approach (async_enabled=false, default)
Claude → Task subagent (background) → Sage (runs sync) → notification
```

**Why this works:**
- CLAUDE.md with strong ALWAYS/NEVER language reliably enforces behavior
- Task subagent can call MCP tools and wait for completion
- Native `<task-notification>` provides clean UX
- Dramatically simpler code path

**CLAUDE.md enforcement:**
```markdown
**ALWAYS** use background Task for: sage_save_checkpoint, sage_save_knowledge, sage_autosave_check
**NEVER** call these directly from the main conversation.
```

---

## Configuration

Add to `SageConfig`:

```python
@dataclass
class SageConfig:
    # ... existing fields ...

    # Async settings
    async_enabled: bool = False         # Sync by default; use CLAUDE.md Task subagent
    notify_success: bool = True         # Show success notifications
    notify_errors: bool = True          # Show error notifications (always recommended)
    worker_timeout: float = 5.0         # Shutdown timeout in seconds
```

---

## Testing Strategy

### Unit Tests

```python
def test_task_queue_fifo():
    """Tasks processed in order."""

def test_worker_handles_failure():
    """Failed task writes error to result file."""

def test_task_result_file_format():
    """Results written as JSON with correct fields."""

def test_get_task_paths_format():
    """Task paths include done and result files."""
```

### Integration Tests

```python
async def test_checkpoint_returns_immediately():
    """sage_save_checkpoint returns before save completes."""
    start = time.time()
    result = await sage_save_checkpoint(...)
    elapsed = time.time() - start
    assert elapsed < 0.1  # Should be instant
    assert "Queued" in result
    assert "POLL:" in result

async def test_result_file_written_on_success():
    """Success result file appears after processing."""
    result = await sage_save_checkpoint(...)
    task_id = extract_task_id(result)
    await asyncio.sleep(3)  # Wait for worker
    assert is_task_complete(task_id)
    assert read_task_result(task_id)["status"] == "success"
```

### Manual Testing

```bash
# Watch task results in real-time
watch -n 0.5 ls ~/.sage/tasks/

# Trigger checkpoint, verify result appears
# In Claude Code, call sage_save_checkpoint
# Then spawn the TRACK command in background
```

---

## Future Enhancements

1. **OS Notifications** - Optional macOS/Linux desktop notifications
2. **Sound alerts** - Terminal bell on errors
3. **Pushover/Ntfy integration** - Mobile push for remote monitoring
4. **Task history** - `sage admin tasks` to view recent task results
5. **Retry logic** - Automatic retry with exponential backoff
6. **Cleanup job** - Periodic cleanup of old task result files
