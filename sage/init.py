"""First-time setup wizard for Sage."""

import os
import shutil
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from sage.config import (
    CONFIG_PATH,
    REFERENCE_DIR,
    SAGE_DIR,
    SHARED_MEMORY_PATH,
    SKILLS_DIR,
    Config,
    ensure_directories,
)
from sage.errors import Result, SageError, err, ok
from sage.skill import create_skill

console = Console()

# Path to bundled reference docs
BUNDLED_REFERENCE = Path(__file__).parent / "reference"


def is_initialized() -> bool:
    """Check if Sage is already initialized."""
    return CONFIG_PATH.exists()


def copy_reference_docs() -> None:
    """Copy bundled reference docs to ~/.sage/reference/."""
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    for doc in BUNDLED_REFERENCE.glob("*.md"):
        dest = REFERENCE_DIR / doc.name
        shutil.copy(doc, dest)


def create_shared_memory() -> None:
    """Create initial shared memory file."""
    if SHARED_MEMORY_PATH.exists():
        return

    content = """# Shared Memory

Insights that inform all research skills.

---

"""
    SHARED_MEMORY_PATH.write_text(content)


def setup_hooks(install: bool = False) -> None:
    """Set up Claude Code hooks for Sage integration."""
    if not install:
        return

    # Copy hook template
    hooks_dir = SAGE_DIR / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    hook_src = Path(__file__).parent / "templates" / "hooks" / "pre-compact.sh"
    hook_dest = hooks_dir / "pre-compact.sh"

    if hook_src.exists():
        shutil.copy(hook_src, hook_dest)
        hook_dest.chmod(0o755)


def run_init(
    api_key: str | None = None,
    install_hooks: bool = False,
    skill_name: str | None = None,
    skill_description: str | None = None,
    non_interactive: bool = False,
) -> Result[None, SageError]:
    """Run the initialization wizard."""

    if is_initialized() and not non_interactive:
        console.print("[yellow]Sage is already configured.[/yellow]")
        if not Confirm.ask("Reinitialize?", default=False):
            return ok(None)

    console.print()
    console.print("[bold]Welcome to Sage[/bold]")
    console.print()

    # Create directory structure
    console.print("Setting up ~/.sage/ ...")
    ensure_directories()

    # API Key
    console.print()
    console.print("[bold]API Key[/bold]")

    final_api_key = api_key
    if not final_api_key:
        env_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_key and not non_interactive:
            if Confirm.ask("  Found ANTHROPIC_API_KEY in environment. Use this?", default=True):
                final_api_key = env_key
        elif env_key:
            final_api_key = env_key

    if not final_api_key and not non_interactive:
        final_api_key = Prompt.ask("  Enter Anthropic API key")

    if final_api_key:
        console.print("  [green]✓[/green] API key configured")
    else:
        console.print("  [yellow]![/yellow] No API key configured. Set ANTHROPIC_API_KEY or run sage config set api-key")

    # Save config
    config = Config(api_key=final_api_key)
    config.save()

    # Reference docs
    console.print()
    console.print("[bold]Reference Docs[/bold]")
    console.print("  Bundling engineering principles...")
    copy_reference_docs()

    for doc in BUNDLED_REFERENCE.glob("*.md"):
        console.print(f"  [green]✓[/green] {doc.name}")

    # Shared memory
    create_shared_memory()

    # Hooks
    console.print()
    console.print("[bold]Claude Code Hooks[/bold]")

    should_install_hooks = install_hooks
    if not non_interactive and not install_hooks:
        should_install_hooks = Confirm.ask(
            "  Install pre-compact hook for session continuity?",
            default=False
        )

    if should_install_hooks:
        setup_hooks(install=True)
        console.print("  [green]✓[/green] Hook installed to ~/.sage/hooks/")
    else:
        console.print("  [dim]Skipped hook installation[/dim]")

    # First skill
    console.print()
    console.print("[bold]First Skill[/bold]")

    should_create_skill = skill_name is not None
    if not non_interactive and not should_create_skill:
        should_create_skill = Confirm.ask(
            "  Create your first research skill?",
            default=True
        )

    if should_create_skill:
        if not skill_name and not non_interactive:
            skill_name = Prompt.ask("  Skill name")

        if skill_name:
            if not skill_description and not non_interactive:
                console.print("  Domain expertise (1-2 sentences):")
                skill_description = Prompt.ask("  >")

            if skill_description:
                result = create_skill(skill_name, skill_description)
                if result.ok:
                    console.print(f"  [green]✓[/green] Created ~/.claude/skills/{skill_name}/SKILL.md")
                    console.print(f"  [green]✓[/green] Created ~/.sage/skills/{skill_name}/")
                else:
                    console.print(f"  [red]✗[/red] {result.error.message}")
    else:
        console.print("  [dim]Skipped skill creation[/dim]")

    # Summary
    console.print()
    console.print("[bold green]Setup complete![/bold green]")
    console.print()
    console.print("Next steps:")
    if skill_name:
        console.print(f'  sage research {skill_name} "your first query"')
        console.print(f"  sage chat {skill_name}")
    else:
        console.print('  sage new <skill> --description "domain expertise"')
    console.print("  sage --help")
    console.print()

    return ok(None)
