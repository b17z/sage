"""Sage CLI - Research orchestration layer for Agent Skills."""

import sys

import click
from rich.console import Console
from rich.table import Table

from sage import __version__
from sage.client import Message, create_client, send_message
from sage.config import SAGE_DIR, Config, SageConfig, ensure_directories, get_sage_config
from sage.errors import format_error
from sage.history import append_entry, calculate_usage, create_entry, read_history
from sage.init import run_init
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
from sage.skill import (
    build_context,
    create_skill,
    get_skill_info,
    list_skills,
    load_skill,
)

console = Console()


@click.group()
@click.version_option(version=__version__)
def main():
    """Sage: Semantic checkpointing for Claude Code."""
    pass


@main.command()
@click.option("--api-key", help="Anthropic API key")
@click.option("--skill", help="Create first skill with this name")
@click.option("--description", help="Skill description (requires --skill)")
@click.option("--non-interactive", is_flag=True, help="Run without prompts")
def init(api_key, skill, description, non_interactive):
    """Initialize Sage (first-time setup). Use 'sage hooks install' for hooks."""
    result = run_init(
        api_key=api_key,
        skill_name=skill,
        skill_description=description,
        non_interactive=non_interactive,
    )
    if not result.ok:
        console.print(f"[red]{format_error(result.error)}[/red]")
        sys.exit(1)


@main.command()
def health():
    """Check Sage system health and diagnostics."""

    from sage.checkpoint import CHECKPOINTS_DIR, list_checkpoints
    from sage.config import CONFIG_PATH, SAGE_DIR, get_sage_config
    from sage.embeddings import check_model_mismatch, get_configured_model, is_available
    from sage.knowledge import KNOWLEDGE_DIR, list_knowledge
    from sage.tasks import TASKS_DIR, load_pending_tasks

    console.print("[bold]Sage Health Check[/bold]")
    console.print("─" * 40)

    issues = []

    # Check .sage directory
    if SAGE_DIR.exists():
        console.print(f"[green]✓[/green] Sage directory: {SAGE_DIR}")
    else:
        console.print(f"[red]✗[/red] Sage directory missing: {SAGE_DIR}")
        issues.append("Run 'sage init' to create directory")

    # Check config
    _ = get_sage_config()  # Validates config loads correctly
    if CONFIG_PATH.exists():
        console.print(f"[green]✓[/green] Config loaded: {CONFIG_PATH}")
    else:
        console.print("[yellow]![/yellow] No config file (using defaults)")

    # Check embeddings
    if is_available():
        model_name = get_configured_model()
        mismatch, old_model, new_model = check_model_mismatch()
        if mismatch:
            console.print(f"[yellow]![/yellow] Embeddings: model changed ({old_model} → {new_model})")
            issues.append("Run 'sage admin rebuild-embeddings' to update")
        else:
            console.print(f"[green]✓[/green] Embeddings: {model_name}")
    else:
        console.print("[yellow]![/yellow] Embeddings: not available (install sentence-transformers)")

    # Check checkpoints
    if CHECKPOINTS_DIR.exists():
        checkpoints = list_checkpoints()
        total_size = sum(f.stat().st_size for f in CHECKPOINTS_DIR.glob("*.md"))
        size_str = f"{total_size / 1024:.1f}KB" if total_size < 1024 * 1024 else f"{total_size / 1024 / 1024:.1f}MB"
        console.print(f"[green]✓[/green] Checkpoints: {len(checkpoints)} saved ({size_str})")
    else:
        console.print("[dim]○[/dim] Checkpoints: none yet")

    # Check knowledge
    if KNOWLEDGE_DIR.exists():
        knowledge = list_knowledge()
        console.print(f"[green]✓[/green] Knowledge: {len(knowledge)} items")
    else:
        console.print("[dim]○[/dim] Knowledge: none yet")

    # Check file permissions
    sensitive_files = [CONFIG_PATH, SAGE_DIR / "tuning.yaml"]
    perm_issues = []
    for f in sensitive_files:
        if f.exists():
            mode = f.stat().st_mode & 0o777
            if mode != 0o600:
                perm_issues.append(f"{f.name}: {oct(mode)} (should be 0o600)")
    if perm_issues:
        console.print(f"[yellow]![/yellow] File permissions: {len(perm_issues)} issue(s)")
        for issue in perm_issues:
            console.print(f"    {issue}")
            issues.append(f"Fix permissions: chmod 600 {issue.split(':')[0]}")
    else:
        console.print("[green]✓[/green] File permissions: OK")

    # Check pending tasks
    if TASKS_DIR.exists():
        pending = load_pending_tasks()
        if pending:
            console.print(f"[yellow]![/yellow] Pending tasks: {len(pending)} from previous session")
            issues.append("Pending tasks will be processed on next MCP server start")
        else:
            console.print("[green]✓[/green] Pending tasks: none")
    else:
        console.print("[dim]○[/dim] Tasks directory: not created yet")

    # Summary
    console.print()
    if issues:
        console.print(f"[yellow]Found {len(issues)} issue(s):[/yellow]")
        for issue in issues:
            console.print(f"  • {issue}")
    else:
        console.print("[green]All systems healthy![/green]")


@main.command()
@click.argument("query")
@click.option("--skill", "-s", default="", help="Skill context for knowledge matching")
@click.option("--knowledge-only", "-k", is_flag=True, help="Only show knowledge matches")
@click.option("--checkpoints-only", "-c", is_flag=True, help="Only show checkpoint matches")
def debug(query, skill, knowledge_only, checkpoints_only):
    """Debug retrieval scoring for a query.

    Shows what knowledge and checkpoints would match, with detailed
    score breakdowns and near-miss analysis for threshold tuning.
    """
    from sage import embeddings
    from sage.checkpoint import _get_checkpoint_embedding_store, list_checkpoints
    from sage.config import get_sage_config
    from sage.knowledge import (
        _get_all_embedding_similarities,
        get_type_threshold,
        load_index,
        score_item_combined,
    )

    config = get_sage_config()
    show_knowledge = not checkpoints_only
    show_checkpoints = not knowledge_only

    console.print(f"[bold]Debug Query:[/bold] \"{query}\"")
    console.print(f"[dim]Skill context: {skill or '(none)'}[/dim]")
    console.print()

    # ─────────────────────────────────────────────────────────────────────────
    # Knowledge Scoring
    # ─────────────────────────────────────────────────────────────────────────
    if show_knowledge:
        console.print("[bold cyan]═══ Knowledge Matches ═══[/bold cyan]")
        console.print(f"[dim]Weights: embedding={config.embedding_weight:.0%}, keyword={config.keyword_weight:.0%}[/dim]")
        console.print()

        items = load_index()
        if not items:
            console.print("[yellow]No knowledge items found.[/yellow]")
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
                console.print(f"[green]Would recall ({len(above)} items):[/green]")
                for item, score, sim, threshold in above:
                    sim_str = f"emb={sim:.2f}" if sim is not None else "emb=N/A"
                    console.print(f"  [green]✓[/green] {item.id}")
                    console.print(f"      score={score:.2f} ({sim_str}) threshold={threshold:.1f} type={item.item_type}")
                    console.print(f"      keywords: {', '.join(item.triggers.keywords[:5])}")
                console.print()
            else:
                console.print("[yellow]No items above threshold.[/yellow]")
                console.print()

            if near_miss:
                console.print(f"[yellow]Near misses ({len(near_miss)} items within 2.0 of threshold):[/yellow]")
                for item, score, sim, threshold in near_miss:
                    sim_str = f"emb={sim:.2f}" if sim is not None else "emb=N/A"
                    gap = threshold - score
                    console.print(f"  [yellow]✗[/yellow] {item.id}")
                    console.print(f"      score={score:.2f} ({sim_str}) threshold={threshold:.1f} gap={gap:.2f}")
                    console.print(f"      keywords: {', '.join(item.triggers.keywords[:5])}")

                # Threshold suggestion
                highest_miss_score = max(s for _, s, _, _ in near_miss)
                suggested = (highest_miss_score / 10.0) - 0.01  # Convert to 0-1 scale
                console.print()
                console.print(f"[dim]Tip: `sage config set recall_threshold {suggested:.2f}` would include more items[/dim]")
                console.print()

    # ─────────────────────────────────────────────────────────────────────────
    # Checkpoint Scoring
    # ─────────────────────────────────────────────────────────────────────────
    if show_checkpoints:
        console.print("[bold cyan]═══ Checkpoint Matches ═══[/bold cyan]")

        if not embeddings.is_available():
            console.print("[yellow]Embeddings not available for checkpoint search.[/yellow]")
        else:
            checkpoints = list_checkpoints(limit=50)
            if not checkpoints:
                console.print("[yellow]No checkpoints found.[/yellow]")
            else:
                # Get query embedding
                result = embeddings.get_query_embedding(query)
                if result.is_err():
                    console.print(f"[red]Failed to embed query: {result.unwrap_err().message}[/red]")
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
                        console.print("[yellow]No checkpoints with embeddings found.[/yellow]")
                    else:
                        scored.sort(key=lambda x: x[1], reverse=True)

                        # Show top matches (similarity > 0.5) and near-misses (0.3-0.5)
                        matches = [(cp, sim) for cp, sim in scored if sim >= 0.5]
                        near_miss = [(cp, sim) for cp, sim in scored if 0.3 <= sim < 0.5]

                        if matches:
                            console.print(f"[green]Relevant checkpoints ({len(matches)}):[/green]")
                            for cp, sim in matches[:5]:
                                console.print(f"  [green]✓[/green] {cp.id} (similarity={sim:.2f})")
                                console.print(f"      {cp.thesis[:80]}...")
                            console.print()
                        else:
                            console.print("[yellow]No highly relevant checkpoints (similarity < 0.5).[/yellow]")
                            console.print()

                        if near_miss:
                            console.print(f"[yellow]Potentially related ({len(near_miss)}):[/yellow]")
                            for cp, sim in near_miss[:3]:
                                console.print(f"  [yellow]~[/yellow] {cp.id} (similarity={sim:.2f})")
                                console.print(f"      {cp.thesis[:80]}...")
                            console.print()


@main.command()
@click.argument("name")
@click.option("--description", "-d", help="Skill domain expertise description")
@click.option("--docs", multiple=True, type=click.Path(exists=True), help="Doc files to include")
def new(name, description, docs):
    """Create a new research skill."""
    ensure_directories()

    # Interactive if no description provided
    if not description:
        console.print(f"[bold]Creating skill: {name}[/bold]")
        console.print()
        description = click.prompt("Describe this skill's domain expertise")

    result = create_skill(name, description)
    if not result.ok:
        console.print(f"[red]{format_error(result.error)}[/red]")
        sys.exit(1)

    console.print(f"[green]✓[/green] Created skill: {name}")
    console.print(f"  Skill: ~/.claude/skills/{name}/SKILL.md")
    console.print(f"  Metadata: ~/.sage/skills/{name}/")

    # Copy docs if provided
    if docs:
        import shutil
        from pathlib import Path

        skill_docs = Path.home() / ".claude" / "skills" / name / "docs"
        for doc in docs:
            src = Path(doc)
            shutil.copy(src, skill_docs / src.name)
            console.print(f"  [green]✓[/green] Added doc: {src.name}")


@main.command()
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def rm(name, force):
    """Delete a research skill."""
    import shutil

    from sage.config import get_sage_skill_path, get_skill_path

    skill_path = get_skill_path(name)
    sage_path = get_sage_skill_path(name)

    if not skill_path.exists():
        console.print(f"[red]Skill '{name}' not found[/red]")
        sys.exit(1)

    if not force:
        if not click.confirm(f"Delete skill '{name}'? This removes all history and sessions."):
            console.print("Cancelled.")
            return

    # Remove both directories
    if skill_path.exists():
        shutil.rmtree(skill_path)
    if sage_path.exists():
        shutil.rmtree(sage_path)

    console.print(f"[green]✓[/green] Deleted skill: {name}")


@main.command()
@click.argument("skill")
@click.argument("query")
@click.option("--no-search", is_flag=True, help="Disable web search")
@click.option("--model", help="Override model")
@click.option("--input", "input_file", type=click.Path(exists=True), help="Read file as context")
@click.option("--output", "output_file", type=click.Path(), help="Write response to file")
@click.option("--stdout", "to_stdout", is_flag=True, help="Write to stdout (for piping)")
def ask(skill, query, no_search, model, input_file, output_file, to_stdout):
    """One-shot question with skill context."""
    config = Config.load()

    # Load skill
    skill_result = load_skill(skill)
    if not skill_result.ok:
        console.print(f"[red]{format_error(skill_result.error)}[/red]")
        sys.exit(1)

    skill_data = skill_result.value

    # Create client
    client_result = create_client(config)
    if not client_result.ok:
        console.print(f"[red]{format_error(client_result.error)}[/red]")
        sys.exit(1)

    client = client_result.value

    # Build context
    system = build_context(skill_data)

    # Recall relevant knowledge
    recall_result = recall_knowledge(query, skill)
    if recall_result.count > 0:
        console.print(f"📚 [dim]Knowledge recalled ({recall_result.count})[/dim]")
        for item in recall_result.items:
            console.print(f"   [dim]├─ {item.id} (~{item.metadata.tokens} tokens)[/dim]")
        system += format_recalled_context(recall_result)

    # Add input file content if provided
    if input_file:
        with open(input_file) as f:
            file_content = f.read()
        query = f"{query}\n\n---\n\nFile content:\n\n{file_content}"

    # Check for stdin
    if not sys.stdin.isatty():
        stdin_content = sys.stdin.read()
        if stdin_content.strip():
            query = f"{query}\n\n---\n\nInput:\n\n{stdin_content}"

    messages = [Message(role="user", content=query)]

    # Output handling
    output_parts = []

    def on_text(text: str):
        output_parts.append(text)
        if not to_stdout and not output_file:
            console.print(text, end="")

    # Send message
    if not to_stdout and not output_file:
        console.print()

    result = send_message(
        client=client,
        system=system,
        messages=messages,
        model=model or config.model,
        enable_search=not no_search,
        on_text=on_text,
    )

    if not result.ok:
        console.print(f"\n[red]{format_error(result.error)}[/red]")
        sys.exit(1)

    response = result.value
    full_output = "".join(output_parts)

    if not to_stdout and not output_file:
        console.print()
        console.print()

    # Write output
    if output_file:
        with open(output_file, "w") as f:
            f.write(full_output)
        console.print(f"[green]✓[/green] Written to {output_file}")
    elif to_stdout:
        print(full_output)

    # Log to history
    entry = create_entry(
        entry_type="ask",
        query=query,
        model=model or config.model,
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        searches=response.searches,
        cache_hits=response.cache_read,
        response=full_output,
    )
    append_entry(skill, entry)


@main.command("list")
def list_cmd():
    """List all Sage-managed skills."""
    skills = list_skills()

    if not skills:
        console.print("[yellow]No skills found.[/yellow]")
        console.print("Create one with: sage new <name>")
        return

    table = Table()
    table.add_column("SKILL")
    table.add_column("DOCS", justify="right")
    table.add_column("HISTORY", justify="right")
    table.add_column("SESSIONS", justify="right")
    table.add_column("LAST ACTIVE")

    for skill_name in skills:
        info_result = get_skill_info(skill_name)
        if not info_result.ok:
            continue

        info = info_result.value
        last_active = info["last_active"]
        if last_active:
            # Format: just date and time
            last_active = last_active[:16].replace("T", " ")

        table.add_row(
            skill_name,
            str(info["doc_count"]),
            str(info["history_count"]),
            str(info["session_count"]),
            last_active or "-",
        )

    console.print(table)

    # Show shared memory count
    from sage.config import SHARED_MEMORY_PATH

    if SHARED_MEMORY_PATH.exists():
        content = SHARED_MEMORY_PATH.read_text()
        # Count lines starting with "- "
        insights = len([l for l in content.split("\n") if l.strip().startswith("- ")])
        if insights:
            console.print()
            console.print(f"Shared memory: {insights} insights")


@main.command()
@click.argument("skill")
@click.option("--limit", "-n", default=20, help="Number of entries to show")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSONL")
def history(skill, limit, as_json):
    """Show query history for a skill."""
    entries = read_history(skill, limit=limit)

    if not entries:
        console.print(f"[yellow]No history for '{skill}'[/yellow]")
        return

    if as_json:
        import json
        from dataclasses import asdict

        for entry in entries:
            print(json.dumps({k: v for k, v in asdict(entry).items() if v is not None}))
        return

    table = Table()
    table.add_column("TIME")
    table.add_column("TYPE")
    table.add_column("QUERY")
    table.add_column("TOKENS", justify="right")
    table.add_column("COST", justify="right")

    for entry in entries:
        ts = entry.ts[:16].replace("T", " ")
        query = entry.query[:50] + "..." if len(entry.query) > 50 else entry.query
        tokens = f"{entry.tokens_in:,} / {entry.tokens_out:,}"
        cost = f"${entry.cost:.2f}" if entry.cost >= 0 else "-"

        table.add_row(ts, entry.type, query, tokens, cost)

    console.print(table)


@main.command()
@click.argument("skill")
@click.argument("index", type=int, default=1)
def show(skill, index):
    """Show full query and response from history.

    INDEX is which entry to show (1 = most recent, 2 = second most recent, etc.)
    """
    entries = read_history(skill, limit=index)

    if not entries or len(entries) < index:
        console.print(f"[yellow]Entry {index} not found in '{skill}' history[/yellow]")
        return

    entry = entries[index - 1]

    console.print()
    console.print(f"[dim]{entry.ts[:19].replace('T', ' ')} | {entry.type} | {entry.model}[/dim]")
    console.print()
    console.print("[bold]Query:[/bold]")
    console.print(entry.query)
    console.print()
    console.print("[bold]Response:[/bold]")
    if entry.response:
        console.print(entry.response)
    else:
        console.print("[dim](Response not stored for this entry)[/dim]")


@main.command()
@click.argument("skill")
def context(skill):
    """Show what a skill knows."""
    # Load skill
    skill_result = load_skill(skill)
    if not skill_result.ok:
        console.print(f"[red]{format_error(skill_result.error)}[/red]")
        sys.exit(1)

    skill_data = skill_result.value
    info_result = get_skill_info(skill)
    info = info_result.value if info_result.ok else {}

    console.print()
    console.print(f"[bold]{'═' * 60}[/bold]")
    console.print(f"[bold]SKILL: {skill}[/bold]")
    console.print(f"[bold]{'═' * 60}[/bold]")

    # Metadata
    console.print()
    console.print("[bold]─── METADATA ───[/bold]")
    console.print(f"name: {skill_data.metadata.name}")
    console.print(f"description: {skill_data.metadata.description[:80]}...")
    console.print(f"version: {skill_data.metadata.version}")
    console.print(f"tags: {', '.join(skill_data.metadata.tags)}")

    # Documents
    console.print()
    console.print(f"[bold]─── DOCUMENTS ({len(skill_data.docs)}) ───[/bold]")
    if skill_data.docs:
        for doc_name, doc_content in skill_data.docs:
            tokens = len(doc_content) // 4
            console.print(f"  {doc_name:<30} {tokens:>6} tokens")
    else:
        console.print("  [dim]No documents[/dim]")

    # Shared memory
    console.print()
    mem_size = info.get("shared_memory_size", 0)
    console.print(f"[bold]─── SHARED MEMORY ({mem_size} tokens) ───[/bold]")
    if skill_data.shared_memory:
        lines = skill_data.shared_memory.strip().split("\n")
        insights = [l for l in lines if l.strip().startswith("- ")]
        for insight in insights[:5]:
            console.print(f"  {insight}")
        if len(insights) > 5:
            console.print(f"  [dim]... and {len(insights) - 5} more[/dim]")
    else:
        console.print("  [dim]No shared memory[/dim]")

    # Recent history
    console.print()
    history = read_history(skill, limit=5)
    console.print(
        f"[bold]─── RECENT HISTORY (last {len(history)} of {info.get('history_count', 0)}) ───[/bold]"
    )
    if history:
        for entry in history:
            ts = entry.ts[:16].replace("T", " ")
            query_preview = entry.query[:50] + "..." if len(entry.query) > 50 else entry.query
            console.print(f"  [{ts}] {entry.type}: {query_preview}")
    else:
        console.print("  [dim]No history[/dim]")

    # Context size estimate
    console.print()
    console.print("[bold]─── CONTEXT SIZE ───[/bold]")
    skill_tokens = len(skill_data.content) // 4
    doc_tokens = sum(len(c) // 4 for _, c in skill_data.docs)
    mem_tokens = info.get("shared_memory_size", 0)
    total = skill_tokens + doc_tokens + mem_tokens

    console.print(f"  Skill + Docs:     {skill_tokens + doc_tokens:>8} tokens (cache-eligible)")
    console.print(f"  Shared Memory:    {mem_tokens:>8} tokens (cache-eligible)")
    console.print("  " + "─" * 40)
    console.print(f"  [bold]Estimated Total: {total:>8} tokens[/bold]")


@main.group()
def config():
    """Manage configuration.

    Sage has two config files:
    - config.yaml: Runtime settings (api_key, model, etc.)
    - tuning.yaml: Retrieval/detection thresholds (recall_threshold, etc.)
    """
    pass


@config.command("list")
def config_list():
    """Show current configuration.

    Examples:
        sage config list
    """
    cfg = Config.load()
    effective = get_sage_config()
    defaults = SageConfig()

    console.print("[bold]Runtime Configuration[/bold] [dim](~/.sage/config.yaml)[/dim]")
    console.print()
    api_display = "[not set]"
    if cfg.api_key:
        api_display = "*" * 20 + cfg.api_key[-8:]
    console.print(f"  api_key: {api_display}")
    console.print(f"  model: {cfg.model}")
    console.print(f"  max_history: {cfg.max_history}")
    console.print(f"  cache_ttl: {cfg.cache_ttl}")

    console.print()
    console.print("[bold]Tuning Configuration[/bold] [dim](tuning.yaml)[/dim]")
    console.print()

    console.print("  [dim]# Retrieval[/dim]")
    _show_tuning_value("recall_threshold", effective.recall_threshold, defaults.recall_threshold)
    _show_tuning_value("dedup_threshold", effective.dedup_threshold, defaults.dedup_threshold)
    _show_tuning_value("embedding_weight", effective.embedding_weight, defaults.embedding_weight)
    _show_tuning_value("keyword_weight", effective.keyword_weight, defaults.keyword_weight)

    console.print("  [dim]# Structural detection[/dim]")
    _show_tuning_value(
        "topic_drift_threshold", effective.topic_drift_threshold, defaults.topic_drift_threshold
    )
    _show_tuning_value(
        "convergence_question_drop",
        effective.convergence_question_drop,
        defaults.convergence_question_drop,
    )
    _show_tuning_value(
        "depth_min_messages", effective.depth_min_messages, defaults.depth_min_messages
    )
    _show_tuning_value("depth_min_tokens", effective.depth_min_tokens, defaults.depth_min_tokens)

    console.print("  [dim]# Model[/dim]")
    _show_tuning_value("embedding_model", effective.embedding_model, defaults.embedding_model)

    console.print()
    console.print("[dim]sage config set KEY VALUE      Set a value[/dim]")
    console.print("[dim]sage config set KEY VALUE --project   Set project-level[/dim]")
    console.print("[dim]sage config reset              Reset tuning to defaults[/dim]")


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--project", is_flag=True, help="Set in project-level config")
def config_set(key: str, value: str, project: bool):
    """Set a configuration value.

    Examples:
        sage config set model claude-opus-4
        sage config set recall_threshold 0.65
        sage config set recall_threshold 0.60 --project
    """
    from pathlib import Path

    # Determine SageConfig location
    if project:
        sage_dir = Path.cwd() / ".sage"
    else:
        sage_dir = SAGE_DIR

    # Load configs
    cfg = Config.load()
    tuning = get_sage_config() if not project else SageConfig.load(sage_dir)

    # Define which keys belong to which config
    legacy_keys = {"api_key", "model", "max_history", "cache_ttl"}
    tuning_keys = {f.name for f in SageConfig.__dataclass_fields__.values()}

    # Normalize key (allow hyphens)
    key = key.replace("-", "_")

    if key in legacy_keys:
        # Runtime Config
        if key == "api_key":
            cfg.api_key = value
        elif key == "model":
            cfg.model = value
        elif key == "max_history":
            try:
                cfg.max_history = int(value)
            except ValueError:
                console.print(f"[red]Invalid integer value: {value}[/red]")
                sys.exit(1)
        elif key == "cache_ttl":
            try:
                cfg.cache_ttl = int(value)
            except ValueError:
                console.print(f"[red]Invalid integer value: {value}[/red]")
                sys.exit(1)
        cfg.save()
        console.print(f"[green]✓[/green] Set {key} (runtime config)")

    elif key in tuning_keys:
        # SageConfig (tuning)
        # Type coercion
        field_type = SageConfig.__dataclass_fields__[key].type
        if field_type == float:
            try:
                typed_value = float(value)
            except ValueError:
                console.print(f"[red]Invalid float value: {value}[/red]")
                sys.exit(1)
        elif field_type == int:
            try:
                typed_value = int(value)
            except ValueError:
                console.print(f"[red]Invalid integer value: {value}[/red]")
                sys.exit(1)
        else:
            typed_value = value

        # Create new config with updated value
        current_dict = tuning.to_dict()
        current_dict[key] = typed_value
        new_tuning = SageConfig(**current_dict)
        new_tuning.save(sage_dir)

        location = "project" if project else "user"
        console.print(f"[green]✓[/green] Set {key} = {typed_value} ({location}-level tuning)")
    else:
        console.print(f"[red]Unknown config key: {key}[/red]")
        console.print()
        console.print("[dim]Runtime keys: api_key, model, max_history, cache_ttl[/dim]")
        console.print(
            "[dim]Tuning keys: recall_threshold, dedup_threshold, embedding_weight, ...[/dim]"
        )
        sys.exit(1)


@config.command("reset")
@click.option("--project", is_flag=True, help="Reset project-level config")
def config_reset(project: bool):
    """Reset tuning configuration to defaults.

    Examples:
        sage config reset
        sage config reset --project
    """
    from pathlib import Path

    if project:
        sage_dir = Path.cwd() / ".sage"
    else:
        sage_dir = SAGE_DIR

    defaults = SageConfig()
    defaults.save(sage_dir)
    location = "project" if project else "user"
    console.print(f"[green]✓[/green] Reset tuning config to defaults ({location}-level)")


def _show_tuning_value(key: str, value, default):
    """Display a tuning value, highlighting if non-default."""
    if value != default:
        console.print(f"  {key}: [cyan]{value}[/cyan] [dim](default: {default})[/dim]")
    else:
        console.print(f"  {key}: {value}")


@main.command()
@click.argument("skill", required=False)
@click.option("--period", default=7, help="Number of days to analyze")
def usage(skill, period):
    """Show usage analytics."""
    skills_to_check = [skill] if skill else list_skills()

    if not skills_to_check:
        console.print("[yellow]No skills found.[/yellow]")
        return

    console.print()
    console.print(f"[bold]{'═' * 60}[/bold]")
    console.print(f"[bold]USAGE: Last {period} days[/bold]")
    console.print(f"[bold]{'═' * 60}[/bold]")
    console.print()

    table = Table()
    table.add_column("SKILL")
    table.add_column("TOKENS IN", justify="right")
    table.add_column("TOKENS OUT", justify="right")
    table.add_column("SEARCHES", justify="right")
    table.add_column("COST", justify="right")

    total_in = 0
    total_out = 0
    total_searches = 0
    total_cost = 0.0
    total_cache = 0

    for s in skills_to_check:
        stats = calculate_usage(s, period)
        if stats["entries"] == 0:
            continue

        total_in += stats["tokens_in"]
        total_out += stats["tokens_out"]
        total_searches += stats["searches"]
        total_cost += stats["cost"]
        total_cache += stats["cache_hits"]

        table.add_row(
            s,
            f"{stats['tokens_in']:,}",
            f"{stats['tokens_out']:,}",
            str(stats["searches"]),
            f"${stats['cost']:.2f}",
        )

    if total_in > 0:
        table.add_section()
        table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{total_in:,}[/bold]",
            f"[bold]{total_out:,}[/bold]",
            f"[bold]{total_searches}[/bold]",
            f"[bold]${total_cost:.2f}[/bold]",
        )

    console.print(table)

    if total_cache > 0:
        console.print()
        console.print("[bold]Cache Statistics:[/bold]")
        cache_rate = (total_cache / total_in * 100) if total_in > 0 else 0
        console.print(f"  Cache-eligible tokens: {total_in:,}")
        console.print(f"  Cache hits:           {total_cache:,} ({cache_rate:.0f}%)")


@main.group()
def knowledge():
    """Manage knowledge items for recall."""
    pass


@knowledge.command("add")
@click.argument("file", type=click.Path(exists=True))
@click.option("--id", "knowledge_id", required=True, help="Unique identifier for this knowledge")
@click.option("--keywords", "-k", required=True, help="Comma-separated trigger keywords")
@click.option("--skill", "-s", help="Scope to specific skill (omit for global)")
@click.option("--source", help="Where this knowledge came from")
def knowledge_add(file, knowledge_id, keywords, skill, source):
    """Add a knowledge item from a file."""
    from pathlib import Path

    content = Path(file).read_text()
    keyword_list = [k.strip() for k in keywords.split(",")]

    item = add_knowledge(
        content=content,
        knowledge_id=knowledge_id,
        keywords=keyword_list,
        skill=skill,
        source=source or "",
    )

    scope = f"skill:{skill}" if skill else "global"
    console.print(f"[green]✓[/green] Added knowledge: {item.id} ({scope})")
    console.print(f"  Keywords: {', '.join(item.triggers.keywords)}")
    console.print(f"  Tokens: ~{item.metadata.tokens}")


@knowledge.command("list")
@click.option("--skill", "-s", help="Filter by skill")
@click.option(
    "--type", "-t", "item_type", help="Filter by type (knowledge, preference, todo, reference)"
)
def knowledge_list(skill, item_type):
    """List knowledge items."""
    items = list_knowledge(skill)

    # Filter by type if specified
    if item_type:
        items = [i for i in items if i.item_type == item_type]

    if not items:
        console.print("[yellow]No knowledge items found.[/yellow]")
        console.print("Add one with: sage knowledge add <file> --id <id> --keywords <kw1,kw2>")
        return

    table = Table()
    table.add_column("ID")
    table.add_column("TYPE")
    table.add_column("SCOPE")
    table.add_column("KEYWORDS")
    table.add_column("TOKENS", justify="right")
    table.add_column("ADDED")

    for item in items:
        scope = ", ".join(item.scope.skills) if item.scope.skills else "global"
        keywords = ", ".join(item.triggers.keywords[:3])
        if len(item.triggers.keywords) > 3:
            keywords += "..."
        type_display = item.item_type
        if item.item_type == "todo" and item.metadata.status:
            type_display = f"todo ({item.metadata.status})"

        table.add_row(
            item.id,
            type_display,
            scope,
            keywords,
            str(item.metadata.tokens),
            item.metadata.added,
        )

    console.print(table)


@knowledge.command("rm")
@click.argument("knowledge_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def knowledge_rm(knowledge_id, force):
    """Remove a knowledge item."""
    if not force:
        if not click.confirm(f"Remove knowledge '{knowledge_id}'?"):
            console.print("Cancelled.")
            return

    if remove_knowledge(knowledge_id):
        console.print(f"[green]✓[/green] Removed: {knowledge_id}")
    else:
        console.print(f"[red]Knowledge '{knowledge_id}' not found[/red]")


@knowledge.command("match")
@click.argument("query")
@click.option("--skill", "-s", default="test", help="Skill context for matching")
def knowledge_match(query, skill):
    """Test what knowledge would be recalled for a query."""
    result = recall_knowledge(query, skill)

    if result.count == 0:
        console.print("[yellow]No knowledge matched this query.[/yellow]")
        return

    console.print(
        f"📚 [bold]Would recall {result.count} items (~{result.total_tokens} tokens):[/bold]"
    )
    for item in result.items:
        console.print(f"  [green]✓[/green] {item.id}")
        console.print(f"    Keywords: {', '.join(item.triggers.keywords)}")
        if item.metadata.source:
            console.print(f"    Source: {item.metadata.source}")


@knowledge.command("edit")
@click.argument("knowledge_id")
@click.option("--content", "-c", help="New content (or use --file)")
@click.option("--file", "-f", "content_file", type=click.Path(exists=True), help="Read new content from file")
@click.option("--keywords", "-k", help="New keywords (comma-separated)")
@click.option("--source", "-s", help="New source attribution")
@click.option("--status", type=click.Choice(["active", "deprecated", "archived"]), help="Set item status")
def knowledge_edit(knowledge_id, content, content_file, keywords, source, status):
    """Edit an existing knowledge item.

    Update content, keywords, source, or status of an existing item.
    Only provided fields are changed; others remain as-is.

    Examples:
        sage knowledge edit my-item --keywords "new,keywords,here"
        sage knowledge edit my-item --file updated-content.md
        sage knowledge edit my-item --status active  # restore archived item
    """
    from sage.knowledge import update_knowledge

    # Handle content from file
    if content_file:
        from pathlib import Path
        content = Path(content_file).read_text()

    # Parse keywords
    kw_list = None
    if keywords:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]

    # Check at least one update
    if content is None and kw_list is None and source is None and status is None:
        console.print("[red]Provide at least one field to update (--content, --keywords, --source, or --status)[/red]")
        sys.exit(1)

    result = update_knowledge(
        knowledge_id=knowledge_id,
        content=content,
        keywords=kw_list,
        source=source,
        status=status,
    )

    if result is None:
        console.print(f"[red]Knowledge item not found: {knowledge_id}[/red]")
        sys.exit(1)

    console.print(f"[green]✓[/green] Updated: {knowledge_id}")
    if content:
        console.print(f"    Content: {len(content)} chars")
    if kw_list:
        console.print(f"    Keywords: {', '.join(kw_list)}")
    if source:
        console.print(f"    Source: {source}")
    if status:
        console.print(f"    Status: {status}")


@knowledge.command("deprecate")
@click.argument("knowledge_id")
@click.option("--reason", "-r", required=True, help="Why this is deprecated")
@click.option("--replacement", help="ID of replacement item")
def knowledge_deprecate(knowledge_id, reason, replacement):
    """Mark a knowledge item as deprecated.

    Deprecated items still appear in search results but show a warning.
    Use this for outdated information you want to flag but not delete.

    Examples:
        sage knowledge deprecate old-api-patterns --reason "API v2 released"
        sage knowledge deprecate old-item --reason "Outdated" --replacement new-item
    """
    from sage.knowledge import deprecate_knowledge

    result = deprecate_knowledge(
        knowledge_id=knowledge_id,
        reason=reason,
        replacement_id=replacement,
    )

    if result is None:
        console.print(f"[red]Knowledge item not found: {knowledge_id}[/red]")
        sys.exit(1)

    console.print(f"[yellow]⚠[/yellow] Deprecated: {knowledge_id}")
    console.print(f"    Reason: {reason}")
    if replacement:
        console.print(f"    Replacement: {replacement}")


@knowledge.command("archive")
@click.argument("knowledge_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def knowledge_archive(knowledge_id, force):
    """Archive a knowledge item (hide from recall).

    Archived items are preserved but excluded from retrieval.
    Use this for obsolete items you want to keep for reference.

    To restore, use: sage knowledge edit <id> --status active
    """
    from sage.knowledge import archive_knowledge, list_knowledge

    # Find item first
    items = list_knowledge()
    item = next((i for i in items if i.id == knowledge_id), None)

    if item is None:
        console.print(f"[red]Knowledge item not found: {knowledge_id}[/red]")
        sys.exit(1)

    if not force:
        click.confirm(
            f"Archive '{knowledge_id}'? It will be hidden from recall.",
            abort=True,
        )

    result = archive_knowledge(knowledge_id)

    if result is None:
        console.print(f"[red]Failed to archive: {knowledge_id}[/red]")
        sys.exit(1)

    console.print(f"[dim]📦[/dim] Archived: {knowledge_id}")
    console.print(f"    [dim]Restore with: sage knowledge edit {knowledge_id} --status active[/dim]")


# ============================================================================
# Todo Commands
# ============================================================================


@main.group()
def todo():
    """Manage persistent todos."""
    pass


@todo.command("list")
@click.option("--all", "show_all", is_flag=True, help="Show all todos (including done)")
def todo_list(show_all):
    """List pending todos."""
    if show_all:
        todos = list_todos()
    else:
        todos = list_todos(status="pending")

    if not todos:
        status_msg = "" if show_all else "pending "
        console.print(f"[yellow]No {status_msg}todos found.[/yellow]")
        console.print("Add one via Claude Code: sage_save_knowledge(..., item_type='todo')")
        return

    table = Table()
    table.add_column("STATUS")
    table.add_column("ID")
    table.add_column("KEYWORDS")
    table.add_column("ADDED")

    for item in todos:
        status_icon = "☐" if item.metadata.status == "pending" else "☑"
        keywords = ", ".join(item.triggers.keywords[:3])
        if len(item.triggers.keywords) > 3:
            keywords += "..."

        table.add_row(
            status_icon,
            item.id,
            keywords,
            item.metadata.added,
        )

    console.print(table)


@todo.command("done")
@click.argument("todo_id")
def todo_done(todo_id):
    """Mark a todo as done."""
    if mark_todo_done(todo_id):
        console.print(f"[green]✓[/green] Marked as done: {todo_id}")
    else:
        console.print(f"[red]Todo '{todo_id}' not found[/red]")


@todo.command("pending")
def todo_pending():
    """Show pending todos (for session start)."""
    todos = get_pending_todos()

    if not todos:
        console.print("[dim]No pending todos.[/dim]")
        return

    console.print("[bold]📋 Pending Todos:[/bold]")
    console.print()

    for item in todos:
        console.print(f"  ☐ [bold]{item.id}[/bold]")
        if item.triggers.keywords:
            console.print(f"    Keywords: {', '.join(item.triggers.keywords[:5])}")

    console.print()
    console.print("[dim]Mark done with: sage todo done <id>[/dim]")


@main.group()
def checkpoint():
    """Manage research checkpoints."""
    pass


@checkpoint.command("list")
@click.option("--skill", "-s", help="Filter by skill")
@click.option("--limit", "-n", default=10, help="Number of checkpoints to show")
def checkpoint_list(skill, limit):
    """List saved checkpoints."""
    from sage.checkpoint import list_checkpoints

    checkpoints = list_checkpoints(skill=skill, limit=limit)

    if not checkpoints:
        console.print("[yellow]No checkpoints found.[/yellow]")
        console.print("Create one with: /checkpoint in Claude Code or sage checkpoint save")
        return

    table = Table()
    table.add_column("ID")
    table.add_column("TRIGGER")
    table.add_column("THESIS")
    table.add_column("CONF", justify="right")
    table.add_column("SAVED")

    for cp in checkpoints:
        thesis = cp.thesis[:40] + "..." if len(cp.thesis) > 40 else cp.thesis
        ts = cp.ts[:16].replace("T", " ")

        table.add_row(
            cp.id[:30] + "..." if len(cp.id) > 30 else cp.id,
            cp.trigger,
            thesis,
            f"{cp.confidence:.0%}",
            ts,
        )

    console.print(table)


@checkpoint.command("show")
@click.argument("checkpoint_id")
def checkpoint_show(checkpoint_id):
    """Show details of a checkpoint."""
    from sage.checkpoint import format_checkpoint_for_context, load_checkpoint

    cp = load_checkpoint(checkpoint_id)

    if not cp:
        console.print(f"[red]Checkpoint '{checkpoint_id}' not found[/red]")
        return

    console.print(format_checkpoint_for_context(cp))


@checkpoint.command("restore")
@click.argument("checkpoint_id")
@click.argument("skill")
def checkpoint_restore(checkpoint_id, skill):
    """Restore a checkpoint and start a query with its context."""
    from sage.checkpoint import format_checkpoint_for_context, load_checkpoint

    cp = load_checkpoint(checkpoint_id)

    if not cp:
        console.print(f"[red]Checkpoint '{checkpoint_id}' not found[/red]")
        return

    # Show what's being restored
    console.print(f"[bold]Restoring checkpoint:[/bold] {cp.id}")
    console.print(
        f"  Thesis: {cp.thesis[:60]}..." if len(cp.thesis) > 60 else f"  Thesis: {cp.thesis}"
    )
    console.print(f"  Confidence: {cp.confidence:.0%}")
    console.print(f"  Open questions: {len(cp.open_questions)}")
    console.print(f"  Sources: {len(cp.sources)}")
    console.print()

    # Format context for injection
    context = format_checkpoint_for_context(cp)
    console.print("[dim]Checkpoint context ready. Use with:[/dim]")
    console.print(
        f'[dim]  sage ask {skill} "<your question>" --input <checkpoint-context-file>[/dim]'
    )
    console.print()
    console.print("[bold]Or copy this context:[/bold]")
    console.print()
    console.print(context)


@checkpoint.command("rm")
@click.argument("checkpoint_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def checkpoint_rm(checkpoint_id, force):
    """Delete a checkpoint."""
    from sage.checkpoint import delete_checkpoint

    if not force:
        if not click.confirm(f"Delete checkpoint '{checkpoint_id}'?"):
            console.print("Cancelled.")
            return

    if delete_checkpoint(checkpoint_id):
        console.print(f"[green]✓[/green] Deleted: {checkpoint_id}")
    else:
        console.print(f"[red]Checkpoint '{checkpoint_id}' not found[/red]")


@main.group()
def hooks():
    """Manage Claude Code hooks for auto-checkpointing."""
    pass


@hooks.command("install")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing hooks")
def hooks_install(force):
    """Install Sage hooks into Claude Code.

    Copies hook scripts to ~/.claude/hooks/ and updates
    ~/.claude/settings.json with the hook configuration.
    """
    import json
    import shutil
    from pathlib import Path

    # Find hook source directory (relative to this package)
    package_dir = Path(__file__).parent.parent
    hooks_src = package_dir / ".claude" / "hooks"

    if not hooks_src.exists():
        # Try installed package location
        import sage

        package_dir = Path(sage.__file__).parent.parent
        hooks_src = package_dir / ".claude" / "hooks"

    if not hooks_src.exists():
        console.print("[red]Could not find hook source files.[/red]")
        console.print("[dim]Expected at: .claude/hooks/ relative to sage package[/dim]")
        sys.exit(1)

    # Destination directories
    hooks_dest = Path.home() / ".claude" / "hooks"
    settings_path = Path.home() / ".claude" / "settings.json"

    # Create hooks directory
    hooks_dest.mkdir(parents=True, exist_ok=True)

    # Copy hook files
    hook_files = [
        "post-response-context-check.sh",
        "post-response-semantic-detector.sh",
        "post-response-sage-notify.sh",
        "pre-compact.sh",
    ]

    copied = []
    for hook_file in hook_files:
        src = hooks_src / hook_file
        dest = hooks_dest / hook_file

        if not src.exists():
            console.print(f"[yellow]Warning: {hook_file} not found in source[/yellow]")
            continue

        if dest.exists() and not force:
            console.print(
                f"[yellow]Skipping {hook_file} (exists, use --force to overwrite)[/yellow]"
            )
            continue

        shutil.copy2(src, dest)
        dest.chmod(0o755)  # Make executable
        copied.append(hook_file)
        console.print(f"[green]✓[/green] Copied {hook_file}")

    # Update settings.json
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            console.print("[yellow]Warning: Could not parse existing settings.json[/yellow]")

    # Build hook configuration with absolute paths
    hook_config = {
        "Stop": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": str(hooks_dest / "post-response-context-check.sh"),
                    },
                    {
                        "type": "command",
                        "command": str(hooks_dest / "post-response-semantic-detector.sh"),
                    },
                    {
                        "type": "command",
                        "command": str(hooks_dest / "post-response-sage-notify.sh"),
                    },
                ],
            }
        ],
        "PreCompact": [
            {
                "matcher": "",
                "hooks": [
                    {"type": "command", "command": str(hooks_dest / "pre-compact.sh")},
                ],
            }
        ],
    }

    # Merge with existing hooks (don't overwrite other hooks)
    if "hooks" not in settings:
        settings["hooks"] = {}

    settings["hooks"].update(hook_config)

    # Write settings
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2))
    console.print(f"[green]✓[/green] Updated {settings_path}")

    console.print()
    console.print("[bold]Sage hooks installed![/bold]")
    console.print("[dim]Restart Claude Code for changes to take effect.[/dim]")


@hooks.command("uninstall")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def hooks_uninstall(force):
    """Remove Sage hooks from Claude Code.

    Removes hook scripts from ~/.claude/hooks/ and removes
    Sage hook configuration from ~/.claude/settings.json.
    """
    import json
    from pathlib import Path

    if not force:
        if not click.confirm("Remove Sage hooks from Claude Code?"):
            console.print("Cancelled.")
            return

    hooks_dest = Path.home() / ".claude" / "hooks"
    settings_path = Path.home() / ".claude" / "settings.json"

    # Remove hook files
    hook_files = [
        "post-response-context-check.sh",
        "post-response-semantic-detector.sh",
        "post-response-sage-notify.sh",
        "pre-compact.sh",
    ]

    for hook_file in hook_files:
        hook_path = hooks_dest / hook_file
        if hook_path.exists():
            hook_path.unlink()
            console.print(f"[green]✓[/green] Removed {hook_file}")

    # Update settings.json
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            if "hooks" in settings:
                # Remove Stop and PreCompact entries that contain our hooks
                if "Stop" in settings["hooks"]:
                    del settings["hooks"]["Stop"]
                if "PreCompact" in settings["hooks"]:
                    del settings["hooks"]["PreCompact"]

                # Clean up empty hooks object
                if not settings["hooks"]:
                    del settings["hooks"]

                settings_path.write_text(json.dumps(settings, indent=2))
                console.print(f"[green]✓[/green] Updated {settings_path}")
        except json.JSONDecodeError:
            console.print("[yellow]Warning: Could not parse settings.json[/yellow]")

    console.print()
    console.print("[bold]Sage hooks uninstalled.[/bold]")


@hooks.command("status")
def hooks_status():
    """Show current hook installation status."""
    import json
    from pathlib import Path

    hooks_dest = Path.home() / ".claude" / "hooks"
    settings_path = Path.home() / ".claude" / "settings.json"

    console.print("[bold]Hook Files:[/bold]")
    hook_files = [
        "post-response-context-check.sh",
        "post-response-semantic-detector.sh",
        "post-response-sage-notify.sh",
        "pre-compact.sh",
    ]

    for hook_file in hook_files:
        hook_path = hooks_dest / hook_file
        if hook_path.exists():
            console.print(f"  [green]✓[/green] {hook_path}")
        else:
            console.print(f"  [red]✗[/red] {hook_path} [dim](not found)[/dim]")

    console.print()
    console.print("[bold]Settings Configuration:[/bold]")
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            hooks_config = settings.get("hooks", {})

            if "Stop" in hooks_config:
                console.print("  [green]✓[/green] Stop hooks configured")
            else:
                console.print("  [red]✗[/red] Stop hooks not configured")

            if "PreCompact" in hooks_config:
                console.print("  [green]✓[/green] PreCompact hooks configured")
            else:
                console.print("  [red]✗[/red] PreCompact hooks not configured")
        except json.JSONDecodeError:
            console.print(f"  [red]✗[/red] Could not parse {settings_path}")
    else:
        console.print(f"  [red]✗[/red] {settings_path} not found")


@main.group()
def mcp():
    """Manage MCP server for Claude Code."""
    pass


@mcp.command("install")
def mcp_install():
    """Install Sage MCP server into Claude Code.

    Adds the sage MCP server to ~/.claude.json so Claude Code
    can use Sage checkpoint and knowledge tools.
    """
    import json
    import shutil
    from pathlib import Path

    claude_json = Path.home() / ".claude.json"

    # Find python executable
    python_path = shutil.which("python") or shutil.which("python3")
    if not python_path:
        console.print("[red]Could not find python executable[/red]")
        sys.exit(1)

    # Load existing config
    config = {}
    if claude_json.exists():
        try:
            config = json.loads(claude_json.read_text())
        except json.JSONDecodeError:
            console.print("[yellow]Warning: Could not parse existing ~/.claude.json[/yellow]")

    # Add MCP server config
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    config["mcpServers"]["sage"] = {
        "type": "stdio",
        "command": python_path,
        "args": ["-m", "sage.mcp_server"],
        "env": {},
    }

    # Write config
    claude_json.write_text(json.dumps(config, indent=2))
    console.print(f"[green]✓[/green] Added sage MCP server to {claude_json}")

    console.print()
    console.print("[bold]Sage MCP server installed![/bold]")
    console.print("[dim]Restart Claude Code for changes to take effect.[/dim]")
    console.print()
    console.print("Available tools:")
    console.print("  • sage_save_checkpoint")
    console.print("  • sage_load_checkpoint")
    console.print("  • sage_list_checkpoints")
    console.print("  • sage_autosave_check")
    console.print("  • sage_save_knowledge")
    console.print("  • sage_recall_knowledge")
    console.print("  • sage_list_knowledge")
    console.print("  • sage_remove_knowledge")


@mcp.command("uninstall")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def mcp_uninstall(force):
    """Remove Sage MCP server from Claude Code."""
    import json
    from pathlib import Path

    if not force:
        if not click.confirm("Remove Sage MCP server from Claude Code?"):
            console.print("Cancelled.")
            return

    claude_json = Path.home() / ".claude.json"

    if not claude_json.exists():
        console.print("[yellow]~/.claude.json not found[/yellow]")
        return

    try:
        config = json.loads(claude_json.read_text())
        if "mcpServers" in config and "sage" in config["mcpServers"]:
            del config["mcpServers"]["sage"]

            # Clean up empty mcpServers
            if not config["mcpServers"]:
                del config["mcpServers"]

            claude_json.write_text(json.dumps(config, indent=2))
            console.print(f"[green]✓[/green] Removed sage MCP server from {claude_json}")
        else:
            console.print("[yellow]Sage MCP server not found in config[/yellow]")
    except json.JSONDecodeError:
        console.print("[red]Could not parse ~/.claude.json[/red]")

    console.print()
    console.print("[bold]Sage MCP server uninstalled.[/bold]")


@mcp.command("status")
def mcp_status():
    """Show MCP server installation status."""
    import json
    from pathlib import Path

    claude_json = Path.home() / ".claude.json"

    console.print("[bold]MCP Server Configuration:[/bold]")

    if not claude_json.exists():
        console.print(f"  [red]✗[/red] {claude_json} not found")
        return

    try:
        config = json.loads(claude_json.read_text())
        mcp_servers = config.get("mcpServers", {})

        if "sage" in mcp_servers:
            sage_config = mcp_servers["sage"]
            console.print("  [green]✓[/green] Sage MCP server configured")
            console.print(f"    Command: {sage_config.get('command', 'N/A')}")
            console.print(f"    Args: {' '.join(sage_config.get('args', []))}")
        else:
            console.print("  [red]✗[/red] Sage MCP server not configured")
            console.print("  [dim]Run 'sage mcp install' to add it[/dim]")
    except json.JSONDecodeError:
        console.print(f"  [red]✗[/red] Could not parse {claude_json}")


# ============================================================================
# Templates Commands
# ============================================================================


@main.group()
def templates():
    """Manage checkpoint templates."""
    pass


@templates.command("list")
def templates_list():
    """List available checkpoint templates."""
    from sage.templates import list_templates, load_template

    template_names = list_templates()

    if not template_names:
        console.print("[yellow]No templates found.[/yellow]")
        return

    table = Table()
    table.add_column("NAME")
    table.add_column("FIELDS")
    table.add_column("DESCRIPTION")

    for name in template_names:
        template = load_template(name)
        if template:
            required_count = sum(1 for f in template.fields if f.required)
            fields_info = f"{len(template.fields)} ({required_count} required)"
            desc = (
                template.description[:40] + "..."
                if len(template.description) > 40
                else template.description
            )
            table.add_row(name, fields_info, desc or "-")

    console.print(table)
    console.print()
    console.print("[dim]Use 'sage templates show <name>' for details[/dim]")


@templates.command("show")
@click.argument("name")
def templates_show(name):
    """Show details of a checkpoint template."""
    from sage.templates import load_template

    template = load_template(name)

    if not template:
        console.print(f"[red]Template '{name}' not found[/red]")
        console.print("[dim]Use 'sage templates list' to see available templates[/dim]")
        return

    console.print()
    console.print(f"[bold]Template: {template.name}[/bold]")
    if template.description:
        console.print(f"[dim]{template.description}[/dim]")
    console.print()

    console.print("[bold]Fields:[/bold]")
    for field in template.fields:
        required = "[cyan]*[/cyan]" if field.required else " "
        console.print(f"  {required} {field.name}")
        if field.description:
            console.print(f"      [dim]{field.description}[/dim]")

    console.print()
    console.print("[dim]* = required field[/dim]")

    if template.jinja_template:
        console.print()
        console.print("[bold]Custom Jinja2 template:[/bold] Yes")



# NOTE: Hooks commands are defined above (after checkpoint commands).
# The hooks group includes: install, uninstall, status
# Hook files managed:
#   - post-response-context-check.sh (context threshold detection)
#   - post-response-semantic-detector.sh (synthesis/branch point detection)
#   - pre-compact.sh (pre-compaction checkpointing)
#   - post-response-sage-notify.sh (notification display)


# ============================================================================
# Admin Commands
# ============================================================================


@main.group()
def admin():
    """Administrative commands for Sage maintenance."""
    pass


@admin.command("rebuild-embeddings")
@click.option("--force", "-f", is_flag=True, help="Rebuild even if model hasn't changed")
def admin_rebuild_embeddings(force):
    """Rebuild all embeddings after model change.

    Use this after changing the embedding_model config to regenerate all
    stored embeddings with the new model. This ensures consistent similarity
    scores across all knowledge items and checkpoints.

    Note: For the MCP server to use the new model, also call sage_reload_config
    via Claude, or restart Claude Code.
    """

    from sage import embeddings
    from sage.checkpoint import list_checkpoints
    from sage.config import get_sage_config
    from sage.knowledge import list_knowledge

    config = get_sage_config()

    # Check for model mismatch
    is_mismatch, stored_model, current_model = embeddings.check_model_mismatch()

    if not is_mismatch and not force:
        console.print(f"[yellow]Embeddings already use {current_model}[/yellow]")
        console.print("[dim]Use --force to rebuild anyway[/dim]")
        return

    if is_mismatch:
        console.print(f"[bold]Model changed: {stored_model} -> {current_model}[/bold]")
    else:
        console.print(f"[bold]Force rebuilding embeddings for: {current_model}[/bold]")

    console.print()

    # Rebuild knowledge embeddings
    knowledge_items = list_knowledge()
    if knowledge_items:
        console.print(f"Rebuilding {len(knowledge_items)} knowledge embeddings...")

        from sage.knowledge import _get_embedding_store, _save_embedding_store

        # Load knowledge store (will be empty due to mismatch detection)
        store = _get_embedding_store()

        # Rebuild each item
        for item in knowledge_items:
            result = embeddings.get_embedding(item.content)
            if result.is_err():
                console.print(f"  [red]✗[/red] {item.id}: {result.unwrap_err().message}")
                continue
            store = store.add(item.id, result.unwrap())
            console.print(f"  [green]✓[/green] {item.id}")

        # Save rebuilt store
        _save_embedding_store(store)
        console.print(f"[green]✓[/green] Saved {len(store)} knowledge embeddings")
    else:
        console.print("[dim]No knowledge items to rebuild[/dim]")

    console.print()

    # Rebuild checkpoint embeddings
    checkpoints = list_checkpoints(limit=100)
    if checkpoints:
        console.print(f"Rebuilding {len(checkpoints)} checkpoint embeddings...")

        from sage.checkpoint import (
            _get_checkpoint_embedding_store,
            _save_checkpoint_embedding_store,
        )

        # Load checkpoint store (will be empty due to mismatch detection)
        store = _get_checkpoint_embedding_store()

        # Rebuild each checkpoint
        for cp in checkpoints:
            result = embeddings.get_embedding(cp.thesis)
            if result.is_err():
                console.print(f"  [red]✗[/red] {cp.id[:30]}: {result.unwrap_err().message}")
                continue
            store = store.add(cp.id, result.unwrap())
            console.print(f"  [green]✓[/green] {cp.id[:30]}...")

        # Save rebuilt store
        _save_checkpoint_embedding_store(store)
        console.print(f"[green]✓[/green] Saved {len(store)} checkpoint embeddings")
    else:
        console.print("[dim]No checkpoints to rebuild[/dim]")

    console.print()
    console.print("[bold]Embeddings rebuilt![/bold]")
    console.print()
    console.print("[dim]If using MCP server, call sage_reload_config via Claude[/dim]")
    console.print("[dim]or restart Claude Code to pick up the new embeddings.[/dim]")


@admin.command("clear-cache")
def admin_clear_cache():
    """Clear all cached data (embeddings, etc.)."""
    from sage.config import SAGE_DIR

    embeddings_dir = SAGE_DIR / "embeddings"

    if not embeddings_dir.exists():
        console.print("[yellow]No cache to clear[/yellow]")
        return

    import shutil

    shutil.rmtree(embeddings_dir)
    console.print(f"[green]✓[/green] Cleared {embeddings_dir}")
    console.print("[dim]Embeddings will be regenerated on next use[/dim]")


# ============================================================================
# Watcher Commands (Session Continuity)
# ============================================================================


@main.group()
def watcher():
    """Manage compaction watcher daemon for session continuity.

    The watcher monitors Claude Code transcripts for compaction events.
    When detected, it writes a marker so the next Sage tool call can
    inject context from the most recent checkpoint.
    """
    pass


@watcher.command("start")
def watcher_start():
    """Start the compaction watcher daemon.

    Runs in the background and watches Claude Code transcripts for
    compaction events (isCompactSummary: true in JSONL).

    When compaction is detected:
    1. Finds the most recent checkpoint
    2. Writes a continuity marker
    3. Next sage tool call injects the checkpoint context
    """
    from sage.watcher import find_active_transcript, start_daemon

    # Check for transcript first
    transcript = find_active_transcript()
    if not transcript:
        console.print("[red]No Claude Code transcript found[/red]")
        console.print("[dim]Start a Claude Code session first[/dim]")
        sys.exit(1)

    console.print(f"[dim]Found transcript: {transcript}[/dim]")

    if start_daemon():
        from sage.watcher import get_watcher_status

        status = get_watcher_status()
        console.print(f"[green]✓[/green] Watcher started (PID {status['pid']})")
        console.print(f"  Watching: {transcript}")
        console.print(f"  Log: {status['log_file']}")
    else:
        from sage.watcher import is_running

        if is_running():
            console.print("[yellow]Watcher already running[/yellow]")
            console.print("[dim]Use 'sage watcher status' for details[/dim]")
        else:
            console.print("[red]Failed to start watcher[/red]")
            console.print("[dim]Check ~/.sage/logs/watcher.log for details[/dim]")
            sys.exit(1)


@watcher.command("stop")
def watcher_stop():
    """Stop the compaction watcher daemon."""
    from sage.watcher import stop_daemon

    if stop_daemon():
        console.print("[green]✓[/green] Watcher stopped")
    else:
        console.print("[yellow]Watcher was not running[/yellow]")


@watcher.command("status")
def watcher_status():
    """Show watcher daemon status."""
    from sage.watcher import get_watcher_status

    status = get_watcher_status()
    config = get_sage_config()

    console.print("[bold]Compaction Watcher Status[/bold]")
    console.print("─" * 40)

    if status["running"]:
        console.print(f"[green]✓[/green] Running (PID {status['pid']})")
    else:
        console.print("[dim]○[/dim] Not running")

    # Show autostart status
    if config.watcher_auto_start:
        console.print("[green]✓[/green] Autostart enabled")
    else:
        console.print("[dim]○[/dim] Autostart disabled")
        console.print("  [dim]Enable: sage watcher autostart enable[/dim]")

    if status.get("transcript"):
        console.print(f"  Transcript: {status['transcript']}")
    else:
        console.print("  [dim]No active transcript found[/dim]")

    console.print(f"  Log file: {status['log_file']}")

    # Show last few log lines if available
    from pathlib import Path

    log_path = Path(status["log_file"])
    if log_path.exists():
        console.print()
        console.print("[bold]Recent log:[/bold]")
        lines = log_path.read_text().strip().split("\n")[-5:]
        for line in lines:
            console.print(f"  [dim]{line}[/dim]")


@watcher.command("autostart")
@click.argument("action", type=click.Choice(["enable", "disable", "status"]))
def watcher_autostart(action):
    """Enable or disable watcher autostart.

    When autostart is enabled, the watcher daemon will automatically
    start on the first MCP tool call of each session.

    Examples:
        sage watcher autostart enable
        sage watcher autostart disable
        sage watcher autostart status
    """
    config = get_sage_config()

    if action == "status":
        if config.watcher_auto_start:
            console.print("[green]✓[/green] Watcher autostart is enabled")
            console.print("  [dim]Watcher will start on first MCP tool call[/dim]")
        else:
            console.print("[dim]○[/dim] Watcher autostart is disabled")
            console.print("  [dim]Enable with: sage watcher autostart enable[/dim]")
        return

    if action == "enable":
        # Update config
        current_dict = config.to_dict()
        current_dict["watcher_auto_start"] = True
        new_config = SageConfig(**current_dict)
        new_config.save(SAGE_DIR)
        console.print("[green]✓[/green] Watcher autostart enabled")
        console.print("  [dim]Watcher will start on first MCP tool call[/dim]")

    elif action == "disable":
        # Update config
        current_dict = config.to_dict()
        current_dict["watcher_auto_start"] = False
        new_config = SageConfig(**current_dict)
        new_config.save(SAGE_DIR)
        console.print("[green]✓[/green] Watcher autostart disabled")


# ============================================================================
# Continuity Commands
# ============================================================================


@main.group()
def continuity():
    """Manage session continuity markers.

    Continuity markers are created by the watcher when compaction is detected.
    The marker tells Sage to inject checkpoint context on the next tool call.
    """
    pass


@continuity.command("status")
def continuity_status():
    """Show current continuity status."""
    from sage.config import get_sage_config
    from sage.continuity import (
        get_continuity_marker,
        get_most_recent_checkpoint,
        has_pending_continuity,
    )
    from sage.watcher import get_watcher_status

    config = get_sage_config()

    console.print("[bold]Session Continuity Status[/bold]")
    console.print("─" * 40)

    # Config status
    if config.continuity_enabled:
        console.print("[green]✓[/green] Continuity enabled")
    else:
        console.print("[yellow]○[/yellow] Continuity disabled")
        console.print("  [dim]Enable: sage config set continuity_enabled true[/dim]")

    # Watcher status
    watcher = get_watcher_status()
    if watcher["running"]:
        console.print(f"[green]✓[/green] Watcher running (PID {watcher['pid']})")
    else:
        console.print("[dim]○[/dim] Watcher not running")
        console.print("  [dim]Start: sage watcher start[/dim]")

    # Pending marker
    console.print()
    if has_pending_continuity():
        marker = get_continuity_marker()
        console.print("[yellow]⚡[/yellow] Pending continuity marker!")
        if marker:
            console.print(f"  Reason: {marker.get('reason', 'unknown')}")
            console.print(f"  Marked at: {marker.get('marked_at', 'unknown')}")
            if marker.get("checkpoint_id"):
                console.print(f"  Checkpoint: {marker['checkpoint_id']}")
            if marker.get("compaction_summary"):
                summary = marker["compaction_summary"][:100]
                console.print(f"  Summary: {summary}...")
        console.print()
        console.print("[dim]Context will be injected on next sage tool call[/dim]")
    else:
        console.print("[dim]○[/dim] No pending continuity")

    # Most recent checkpoint
    console.print()
    recent_cp = get_most_recent_checkpoint()
    if recent_cp:
        console.print(f"[dim]Most recent checkpoint: {recent_cp.name}[/dim]")
    else:
        console.print("[dim]No checkpoints saved yet[/dim]")


@continuity.command("clear")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def continuity_clear(force):
    """Clear pending continuity marker.

    Use this if you want to skip automatic context injection after compaction.
    """
    from sage.continuity import clear_continuity, has_pending_continuity

    if not has_pending_continuity():
        console.print("[yellow]No pending continuity marker[/yellow]")
        return

    if not force:
        if not click.confirm("Clear pending continuity marker?"):
            console.print("Cancelled.")
            return

    clear_continuity()
    console.print("[green]✓[/green] Continuity marker cleared")


@continuity.command("mark")
@click.option("--reason", "-r", default="manual", help="Reason for marking")
def continuity_mark(reason):
    """Manually create a continuity marker.

    This is mainly for testing. The marker will trigger context injection
    on the next sage MCP tool call.
    """
    from sage.continuity import mark_for_continuity

    result = mark_for_continuity(reason=reason)

    if result.ok:
        console.print("[green]✓[/green] Continuity marker created")
        console.print(f"  Reason: {reason}")
        console.print(f"  Marker: {result.value}")
        console.print()
        console.print("[dim]Context will be injected on next sage tool call[/dim]")
    else:
        console.print(f"[red]Failed to create marker: {result.unwrap_err().message}[/red]")
        sys.exit(1)


# ============================================================================
# Skills Commands (Sage Methodology Skills)
# ============================================================================


@main.group()
def skills():
    """Manage Sage methodology skills.

    Sage ships default skills that teach Claude how to use Sage effectively.
    These are separate from research skills created via 'sage create'.

    Skills are installed to ~/.claude/skills/sage/
    """
    pass


@skills.command("install")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing skills")
def skills_install(force):
    """Install default Sage methodology skills.

    Installs:
    - sage-memory: Background Task pattern for saves
    - sage-research: Checkpoint methodology
    - sage-session: Session start ritual

    Skills are installed to ~/.claude/skills/sage/
    """
    from sage.default_skills import SAGE_SKILLS_DIR, install_all_skills

    console.print("[bold]Installing Sage Skills[/bold]")
    console.print(f"Location: {SAGE_SKILLS_DIR}")
    console.print("─" * 40)

    results = install_all_skills(force=force)

    for skill_name, success, message in results:
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[yellow]○[/yellow] {message}")

    console.print()
    console.print("[dim]Skills will be loaded by Claude when context matches triggers.[/dim]")


@skills.command("list")
def skills_list():
    """List installed Sage methodology skills."""
    from sage.default_skills import (
        SAGE_SKILLS_DIR,
        check_skill_version,
        get_default_skills,
        get_installed_sage_skills,
    )

    installed = get_installed_sage_skills()

    if not installed:
        console.print("[yellow]No Sage skills installed.[/yellow]")
        console.print("Install with: sage skills install")
        return

    console.print(f"[bold]Installed Sage Skills[/bold] ({SAGE_SKILLS_DIR})")
    console.print("─" * 50)

    table = Table()
    table.add_column("SKILL")
    table.add_column("VERSION")
    table.add_column("STATUS")

    available_names = [s.name for s in get_default_skills()]

    for skill_name in installed:
        installed_ver, available_ver = check_skill_version(skill_name)

        if skill_name not in available_names:
            status = "[dim]custom[/dim]"
        elif installed_ver == available_ver:
            status = "[green]up to date[/green]"
        else:
            status = f"[yellow]update available ({available_ver})[/yellow]"

        table.add_row(skill_name, installed_ver or "-", status)

    console.print(table)


@skills.command("update")
def skills_update():
    """Update Sage methodology skills to latest versions."""
    from sage.default_skills import install_all_skills

    console.print("[bold]Updating Sage Skills[/bold]")
    console.print("─" * 40)

    results = install_all_skills(force=True)

    for skill_name, success, message in results:
        if success:
            console.print(f"[green]✓[/green] {message}")
        else:
            console.print(f"[red]✗[/red] {message}")

    console.print()
    console.print("[green]Skills updated to latest versions.[/green]")


@skills.command("show")
@click.argument("name")
def skills_show(name):
    """Show a Sage methodology skill's content.

    Security: skill name is sanitized to prevent path traversal.
    """
    from sage.default_skills import get_skill_path

    skill_path = get_skill_path(name)

    if not skill_path.exists():
        console.print(f"[red]Skill not found: {name}[/red]")
        console.print(f"  Expected: {skill_path}")
        sys.exit(1)

    content = skill_path.read_text()
    console.print(content)


if __name__ == "__main__":
    main()
