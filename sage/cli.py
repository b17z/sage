"""Sage CLI - Research orchestration layer for Agent Skills."""

import sys

import click
from rich.console import Console
from rich.table import Table

from sage import __version__
from sage.client import Message, create_client, send_message
from sage.config import Config, ensure_directories
from sage.errors import format_error
from sage.history import append_entry, calculate_usage, create_entry, read_history
from sage.init import run_init
from sage.knowledge import (
    add_knowledge,
    format_recalled_context,
    list_knowledge,
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
    """Sage: Research orchestration layer for Agent Skills."""
    pass


@main.command()
@click.option("--api-key", help="Anthropic API key")
@click.option("--hooks/--no-hooks", default=None, help="Install Claude Code hooks")
@click.option("--skill", help="Create first skill with this name")
@click.option("--description", help="Skill description (requires --skill)")
@click.option("--non-interactive", is_flag=True, help="Run without prompts")
def init(api_key, hooks, skill, description, non_interactive):
    """Initialize Sage (first-time setup)."""
    result = run_init(
        api_key=api_key,
        install_hooks=hooks or False,
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
    from sage.config import get_sage_skill_path, get_skill_path
    import shutil

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


@main.command()
@click.option("--set", "set_value", nargs=2, help="Set a config value: --set KEY VALUE")
def config(set_value):
    """Manage configuration."""
    cfg = Config.load()

    if set_value:
        key, value = set_value
        key = key.replace("-", "_")

        if key == "api_key":
            cfg.api_key = value
        elif key == "model":
            cfg.model = value
        elif key == "default_depth":
            cfg.default_depth = value
        elif key == "max_history":
            cfg.max_history = int(value)
        else:
            console.print(f"[red]Unknown config key: {key}[/red]")
            sys.exit(1)

        cfg.save()
        console.print(f"[green]✓[/green] Set {key}")
    else:
        # Show config
        console.print("[bold]Current Configuration[/bold]")
        console.print()
        api_display = '[not set]'
        if cfg.api_key:
            api_display = '*' * 20 + cfg.api_key[-8:]
        console.print(f"  api_key: {api_display}")
        console.print(f"  model: {cfg.model}")
        console.print(f"  default_depth: {cfg.default_depth}")
        console.print(f"  max_history: {cfg.max_history}")
        console.print(f"  cache_ttl: {cfg.cache_ttl}")
        console.print()
        console.print("[dim]Use --set KEY VALUE to change settings[/dim]")


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
def knowledge_list(skill):
    """List knowledge items."""
    items = list_knowledge(skill)
    
    if not items:
        console.print("[yellow]No knowledge items found.[/yellow]")
        console.print("Add one with: sage knowledge add <file> --id <id> --keywords <kw1,kw2>")
        return
    
    table = Table()
    table.add_column("ID")
    table.add_column("SCOPE")
    table.add_column("KEYWORDS")
    table.add_column("TOKENS", justify="right")
    table.add_column("ADDED")
    
    for item in items:
        scope = ", ".join(item.scope.skills) if item.scope.skills else "global"
        keywords = ", ".join(item.triggers.keywords[:3])
        if len(item.triggers.keywords) > 3:
            keywords += "..."
        
        table.add_row(
            item.id,
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


if __name__ == "__main__":
    main()
