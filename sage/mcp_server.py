"""Sage MCP Server.

Exposes checkpoint and knowledge operations as MCP tools for Claude Code.

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

from mcp.server.fastmcp import FastMCP

from sage.config import detect_project_root
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
    KNOWLEDGE_TYPES,
    add_knowledge,
    format_recalled_context,
    get_pending_todos,
    list_knowledge,
    list_todos,
    mark_todo_done,
    recall_knowledge,
    remove_knowledge,
)

# Initialize MCP server
mcp = FastMCP("sage")

# Detect project root at startup for project-local checkpoints
_PROJECT_ROOT = detect_project_root()


# =============================================================================
# Checkpoint Tools
# =============================================================================


@mcp.tool()
def sage_save_checkpoint(
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
        Confirmation message with checkpoint ID
    """
    # Validate confidence bounds
    if not (0.0 <= confidence <= 1.0):
        return f"⏸ Invalid confidence {confidence}: must be between 0.0 and 1.0"

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
    }

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
def sage_save_knowledge(
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
        Confirmation message
    """
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
def sage_autosave_check(
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
        Confirmation if saved, or explanation if not saved
    """
    from sage.config import get_sage_config

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
    dedup_result = is_duplicate_checkpoint(current_thesis, project_path=_PROJECT_ROOT)
    if dedup_result.is_duplicate:
        return (
            f"⏸ Not saving: semantically similar to recent checkpoint "
            f"({dedup_result.similarity_score:.0%} similarity).\n"
            f"Similar: {dedup_result.similar_checkpoint_id}"
        )

    # Save the checkpoint
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
    }

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

    thesis_preview = current_thesis[:50] + "..." if len(current_thesis) > 50 else current_thesis
    thesis_preview = thesis_preview.replace("\n", " ")

    return f"📍 Autosaved: {thesis_preview}\nCheckpoint: {checkpoint.id}"


# =============================================================================
# Entry Point
# =============================================================================


def main():
    """Run the Sage MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
