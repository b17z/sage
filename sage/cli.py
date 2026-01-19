"""Sage CLI - Research orchestration layer for Agent Skills."""

import sys

import click
from rich.console import Console
from rich.table import Table

from sage import __version__
from sage.client import Message, create_client, send_message
from sage.config import Config, SageConfig, ensure_directories, get_sage_config, SAGE_DIR
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
    console.print(f"[bold]─── RECENT HISTORY (last {len(history)} of {info.get('history_count', 0)}) ───[/bold]")
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
    _show_tuning_value("topic_drift_threshold", effective.topic_drift_threshold, defaults.topic_drift_threshold)
    _show_tuning_value("convergence_question_drop", effective.convergence_question_drop, defaults.convergence_question_drop)
    _show_tuning_value("depth_min_messages", effective.depth_min_messages, defaults.depth_min_messages)
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
        console.print("[dim]Tuning keys: recall_threshold, dedup_threshold, embedding_weight, ...[/dim]")
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
@click.option("--type", "-t", "item_type", help="Filter by type (knowledge, preference, todo, reference)")
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

    console.print(f"📚 [bold]Would recall {result.count} items (~{result.total_tokens} tokens):[/bold]")
    for item in result.items:
        console.print(f"  [green]✓[/green] {item.id}")
        console.print(f"    Keywords: {', '.join(item.triggers.keywords)}")
        if item.metadata.source:
            console.print(f"    Source: {item.metadata.source}")


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
    console.print(f"  Thesis: {cp.thesis[:60]}..." if len(cp.thesis) > 60 else f"  Thesis: {cp.thesis}")
    console.print(f"  Confidence: {cp.confidence:.0%}")
    console.print(f"  Open questions: {len(cp.open_questions)}")
    console.print(f"  Sources: {len(cp.sources)}")
    console.print()

    # Format context for injection
    context = format_checkpoint_for_context(cp)
    console.print("[dim]Checkpoint context ready. Use with:[/dim]")
    console.print(f"[dim]  sage ask {skill} \"<your question>\" --input <checkpoint-context-file>[/dim]")
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
            console.print(f"[yellow]Skipping {hook_file} (exists, use --force to overwrite)[/yellow]")
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
                    {"type": "command", "command": str(hooks_dest / "post-response-context-check.sh")},
                    {"type": "command", "command": str(hooks_dest / "post-response-semantic-detector.sh")},
                ]
            }
        ],
        "PreCompact": [
            {
                "matcher": "",
                "hooks": [
                    {"type": "command", "command": str(hooks_dest / "pre-compact.sh")},
                ]
            }
        ]
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
        "env": {}
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
            desc = template.description[:40] + "..." if len(template.description) > 40 else template.description
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


if __name__ == "__main__":
    main()
