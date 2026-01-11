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

from sage.checkpoint import (
    create_checkpoint_from_dict,
    format_checkpoint_for_context,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)
from sage.knowledge import (
    add_knowledge,
    format_recalled_context,
    list_knowledge,
    recall_knowledge,
    remove_knowledge,
)

# Initialize MCP server
mcp = FastMCP("sage")


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

    Returns:
        Confirmation message with checkpoint ID
    """
    data = {
        "core_question": core_question,
        "thesis": thesis,
        "confidence": confidence,
        "open_questions": open_questions or [],
        "sources": sources or [],
        "tensions": tensions or [],
        "unique_contributions": unique_contributions or [],
        "action": {"goal": action_goal, "type": action_type},
    }

    checkpoint = create_checkpoint_from_dict(data, trigger=trigger)
    path = save_checkpoint(checkpoint)

    return f"✓ Checkpoint saved: {checkpoint.id}\nPath: {path}"


@mcp.tool()
def sage_list_checkpoints(limit: int = 10, skill: str | None = None) -> str:
    """List saved research checkpoints.

    Args:
        limit: Maximum number of checkpoints to return
        skill: Optional skill filter

    Returns:
        Formatted list of checkpoints with ID, thesis, confidence, and date
    """
    checkpoints = list_checkpoints(skill=skill, limit=limit)

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
    checkpoint = load_checkpoint(checkpoint_id)

    if not checkpoint:
        return f"Checkpoint not found: {checkpoint_id}"

    return format_checkpoint_for_context(checkpoint)


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

    Returns:
        Confirmation message
    """
    item = add_knowledge(
        content=content,
        knowledge_id=knowledge_id,
        keywords=keywords,
        skill=skill,
        source=source,
    )

    scope = f"skill:{skill}" if skill else "global"
    return f"✓ Knowledge saved: {item.id} ({scope}, ~{item.metadata.tokens} tokens)"


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
    result = recall_knowledge(query, skill)

    if result.count == 0:
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
        lines.append(f"- **{item.id}** ({scope})")
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
# Entry Point
# =============================================================================


def main():
    """Run the Sage MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
