"""Checkpoint template system for Sage.

Supports custom checkpoint schemas via YAML field definitions and optional
Jinja2 templates for output formatting.

Templates are loaded from:
1. Built-in templates in sage/templates/ (shipped with package)
2. User templates in .sage/templates/ (override built-in)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment

from sage.config import SAGE_DIR, detect_project_root

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

# Built-in templates directory (relative to this file)
BUILTIN_TEMPLATES_DIR = Path(__file__).parent / "templates"

# User templates directory
USER_TEMPLATES_DIR = SAGE_DIR / "templates"


# ============================================================================
# Template Data Classes
# ============================================================================


@dataclass(frozen=True)
class TemplateField:
    """A field definition in a checkpoint template."""

    name: str
    required: bool = False
    default: Any = None
    description: str = ""


@dataclass(frozen=True)
class CheckpointTemplate:
    """A checkpoint template definition."""

    name: str
    fields: tuple[TemplateField, ...]
    description: str = ""
    jinja_template: str | None = None  # Raw Jinja2 template string if provided


# ============================================================================
# Security
# ============================================================================


def _sanitize_template_name(name: str) -> str:
    """Sanitize a template name to prevent path traversal.

    Only allows alphanumeric, hyphens, underscores.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")
    return sanitized or "default"


def _is_safe_path(base: Path, target: Path) -> bool:
    """Check if target path is safely within base directory."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


# ============================================================================
# Template Loading
# ============================================================================


def _get_templates_dirs() -> list[Path]:
    """Get template directories in priority order (user overrides built-in)."""
    dirs = []

    # Project-local templates (highest priority)
    project_root = detect_project_root()
    if project_root:
        project_templates = project_root / ".sage" / "templates"
        if project_templates.exists():
            dirs.append(project_templates)

    # User templates
    if USER_TEMPLATES_DIR.exists():
        dirs.append(USER_TEMPLATES_DIR)

    # Built-in templates (lowest priority)
    if BUILTIN_TEMPLATES_DIR.exists():
        dirs.append(BUILTIN_TEMPLATES_DIR)

    return dirs


def _load_yaml_template(path: Path) -> dict | None:
    """Load a template YAML file safely."""
    if not path.exists():
        return None

    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.warning(f"Invalid YAML in template {path}: {e}")
        return None


def _load_jinja_template(path: Path) -> str | None:
    """Load a Jinja2 template file."""
    if not path.exists():
        return None

    try:
        return path.read_text()
    except OSError as e:
        logger.warning(f"Failed to load Jinja template {path}: {e}")
        return None


def _parse_template_yaml(data: dict, jinja_template: str | None = None) -> CheckpointTemplate:
    """Parse a template YAML dict into a CheckpointTemplate."""
    name = data.get("name", "unknown")
    description = data.get("description", "")

    fields = []
    for field_data in data.get("fields", []):
        if isinstance(field_data, dict):
            field = TemplateField(
                name=field_data.get("name", ""),
                required=field_data.get("required", False),
                default=field_data.get("default"),
                description=field_data.get("description", ""),
            )
        elif isinstance(field_data, str):
            # Simple field name string
            field = TemplateField(name=field_data)
        else:
            continue

        if field.name:
            fields.append(field)

    return CheckpointTemplate(
        name=name,
        fields=tuple(fields),
        description=description,
        jinja_template=jinja_template,
    )


def load_template(name: str) -> CheckpointTemplate | None:
    """Load a template by name.

    Looks in template directories in priority order:
    1. Project-local .sage/templates/
    2. User ~/.sage/templates/
    3. Built-in sage/templates/

    Args:
        name: Template name (without extension)

    Returns:
        CheckpointTemplate or None if not found
    """
    safe_name = _sanitize_template_name(name)

    for templates_dir in _get_templates_dirs():
        # Check for YAML config
        yaml_path = templates_dir / f"{safe_name}.yaml"
        jinja_path = templates_dir / f"{safe_name}.md.j2"

        # Security check
        if not _is_safe_path(templates_dir, yaml_path):
            continue
        if not _is_safe_path(templates_dir, jinja_path):
            continue

        yaml_data = _load_yaml_template(yaml_path)
        if yaml_data:
            jinja_template = _load_jinja_template(jinja_path)
            return _parse_template_yaml(yaml_data, jinja_template)

    return None


def list_templates() -> list[str]:
    """List available template names."""
    templates = set()

    for templates_dir in _get_templates_dirs():
        if not templates_dir.exists():
            continue

        for path in templates_dir.glob("*.yaml"):
            templates.add(path.stem)

    return sorted(templates)


def get_default_template() -> CheckpointTemplate:
    """Get the default template (current checkpoint format)."""
    template = load_template("default")
    if template:
        return template

    # Fallback if default.yaml doesn't exist
    return CheckpointTemplate(
        name="default",
        fields=(
            TemplateField(name="core_question", required=True),
            TemplateField(name="thesis", required=True),
            TemplateField(name="confidence", required=True),
            TemplateField(name="key_evidence"),
            TemplateField(name="reasoning_trace"),
            TemplateField(name="open_questions"),
            TemplateField(name="sources"),
            TemplateField(name="tensions"),
            TemplateField(name="unique_contributions"),
        ),
        description="Default checkpoint template",
    )


# ============================================================================
# Template Validation
# ============================================================================


@dataclass
class ValidationResult:
    """Result of template validation."""

    valid: bool
    errors: list[str]
    warnings: list[str]


def validate_checkpoint_data(
    data: dict[str, Any],
    template: CheckpointTemplate,
) -> ValidationResult:
    """Validate checkpoint data against a template.

    Args:
        data: Checkpoint data dict
        template: Template to validate against

    Returns:
        ValidationResult with errors and warnings
    """
    errors = []
    warnings = []

    # Check required fields
    for field in template.fields:
        if field.required and field.name not in data:
            errors.append(f"Missing required field: {field.name}")
        elif field.required and not data.get(field.name):
            errors.append(f"Required field is empty: {field.name}")

    # Check for unknown fields (warning only)
    known_fields = {f.name for f in template.fields}
    # Also allow standard metadata fields
    known_fields.update(
        {
            "id",
            "ts",
            "trigger",
            "skill",
            "project",
            "parent_checkpoint",
            "message_count",
            "token_estimate",
            "action_goal",
            "action_type",
            "template",
            "custom_fields",
        }
    )

    for key in data:
        if key not in known_fields:
            warnings.append(f"Unknown field: {key}")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ============================================================================
# Template Rendering
# ============================================================================


def _create_sandbox_env() -> SandboxedEnvironment:
    """Create a sandboxed Jinja2 environment for safe template rendering."""
    env = SandboxedEnvironment(
        autoescape=False,  # Markdown doesn't need HTML escaping
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Add safe filters
    env.filters["default"] = lambda v, d: v if v else d
    env.filters["join"] = lambda v, sep=", ": sep.join(str(x) for x in v) if v else ""

    return env


def render_checkpoint(
    data: dict[str, Any],
    template: CheckpointTemplate,
) -> str:
    """Render checkpoint data using a template.

    If the template has a Jinja2 template, uses that.
    Otherwise, uses the default markdown renderer.

    Args:
        data: Checkpoint data dict
        template: Template to use

    Returns:
        Rendered markdown string
    """
    if template.jinja_template:
        return _render_with_jinja(data, template)
    else:
        return _render_default_markdown(data, template)


def _render_with_jinja(data: dict[str, Any], template: CheckpointTemplate) -> str:
    """Render checkpoint using Jinja2 template."""
    if not template.jinja_template:
        return _render_default_markdown(data, template)

    try:
        env = _create_sandbox_env()
        jinja_template = env.from_string(template.jinja_template)

        # Prepare context
        context = {
            "id": data.get("id", ""),
            "timestamp": data.get("ts", ""),
            "template_name": template.name,
            **data,
        }

        return jinja_template.render(**context)
    except TemplateError as e:
        logger.warning(f"Jinja template error: {e}, falling back to default")
        return _render_default_markdown(data, template)


def _render_default_markdown(data: dict[str, Any], template: CheckpointTemplate) -> str:
    """Render checkpoint using default markdown format."""
    parts = []

    # YAML frontmatter
    frontmatter = {
        "id": data.get("id", ""),
        "type": template.name,
        "ts": data.get("ts", ""),
        "trigger": data.get("trigger", "manual"),
        "confidence": data.get("confidence", 0.0),
    }

    # Add optional metadata
    for key in [
        "skill",
        "project",
        "parent_checkpoint",
        "message_count",
        "token_estimate",
        "action_goal",
        "action_type",
    ]:
        if data.get(key):
            frontmatter[key] = data[key]

    fm_yaml = yaml.safe_dump(frontmatter, default_flow_style=False, sort_keys=False)
    parts.append(f"---\n{fm_yaml}---\n")

    # Core question (if present)
    if data.get("core_question"):
        parts.append(f"# {data['core_question']}\n\n")

    # Thesis
    if data.get("thesis"):
        parts.append(f"## Thesis\n\n{data['thesis']}\n\n")

    # Decision (for decision template)
    if data.get("decision"):
        parts.append(f"## Decision\n\n{data['decision']}\n\n")

    # Summary (for code-review template)
    if data.get("summary"):
        parts.append(f"## Summary\n\n{data['summary']}\n\n")

    # Key Evidence
    if data.get("key_evidence"):
        parts.append("## Key Evidence\n\n")
        for evidence in data["key_evidence"]:
            parts.append(f"- {evidence}\n")
        parts.append("\n")

    # Reasoning Trace
    if data.get("reasoning_trace"):
        parts.append(f"## Reasoning Trace\n\n{data['reasoning_trace']}\n\n")

    # Options Considered (for decision template)
    if data.get("options_considered"):
        parts.append("## Options Considered\n\n")
        for opt in data["options_considered"]:
            parts.append(f"- {opt}\n")
        parts.append("\n")

    # Tradeoffs (for decision template)
    if data.get("tradeoffs"):
        parts.append(f"## Tradeoffs\n\n{data['tradeoffs']}\n\n")

    # Recommendation (for decision template)
    if data.get("recommendation"):
        parts.append(f"## Recommendation\n\n{data['recommendation']}\n\n")

    # Risks (for decision template)
    if data.get("risks"):
        parts.append("## Risks\n\n")
        if isinstance(data["risks"], list):
            for risk in data["risks"]:
                parts.append(f"- {risk}\n")
        else:
            parts.append(f"{data['risks']}\n")
        parts.append("\n")

    # Issues Found (for code-review template)
    if data.get("issues_found"):
        parts.append("## Issues Found\n\n")
        for issue in data["issues_found"]:
            parts.append(f"- {issue}\n")
        parts.append("\n")

    # Suggestions (for code-review template)
    if data.get("suggestions"):
        parts.append("## Suggestions\n\n")
        for suggestion in data["suggestions"]:
            parts.append(f"- {suggestion}\n")
        parts.append("\n")

    # Files Reviewed (for code-review template)
    if data.get("files_reviewed"):
        parts.append("## Files Reviewed\n\n")
        for file in data["files_reviewed"]:
            parts.append(f"- {file}\n")
        parts.append("\n")

    # Open Questions
    if data.get("open_questions"):
        parts.append("## Open Questions\n\n")
        for q in data["open_questions"]:
            parts.append(f"- {q}\n")
        parts.append("\n")

    # Sources
    if data.get("sources"):
        parts.append("## Sources\n\n")
        for src in data["sources"]:
            if isinstance(src, dict):
                src_id = src.get("id", "unknown")
                src_type = src.get("type", "")
                take = src.get("take", "")
                relation = src.get("relation", "")
                parts.append(f"- **{src_id}** ({src_type}): {take}")
                if relation:
                    parts.append(f" — _{relation}_")
                parts.append("\n")
            else:
                parts.append(f"- {src}\n")
        parts.append("\n")

    # Tensions
    if data.get("tensions"):
        parts.append("## Tensions\n\n")
        for tension in data["tensions"]:
            if isinstance(tension, dict):
                between = tension.get("between", ["?", "?"])
                nature = tension.get("nature", "")
                resolution = tension.get("resolution", "")
                parts.append(f"- **{between[0]}** vs **{between[1]}**: {nature}")
                if resolution:
                    parts.append(f" — _{resolution}_")
                parts.append("\n")
            else:
                parts.append(f"- {tension}\n")
        parts.append("\n")

    # Unique Contributions
    if data.get("unique_contributions"):
        parts.append("## Unique Contributions\n\n")
        for contrib in data["unique_contributions"]:
            if isinstance(contrib, dict):
                c_type = contrib.get("type", "")
                content = contrib.get("content", "")
                parts.append(f"- **{c_type}**: {content}\n")
            else:
                parts.append(f"- {contrib}\n")
        parts.append("\n")

    # Custom fields (for extensibility)
    if data.get("custom_fields"):
        parts.append("## Custom Fields\n\n")
        for key, value in data["custom_fields"].items():
            if isinstance(value, list):
                parts.append(f"### {key}\n\n")
                for item in value:
                    parts.append(f"- {item}\n")
                parts.append("\n")
            else:
                parts.append(f"**{key}:** {value}\n\n")

    return "".join(parts)


# ============================================================================
# User Template Management
# ============================================================================


def ensure_user_templates_dir() -> Path:
    """Ensure user templates directory exists."""
    USER_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return USER_TEMPLATES_DIR


def save_user_template(name: str, yaml_content: str, jinja_content: str | None = None) -> bool:
    """Save a user template.

    Args:
        name: Template name
        yaml_content: YAML configuration content
        jinja_content: Optional Jinja2 template content

    Returns:
        True if saved successfully
    """
    safe_name = _sanitize_template_name(name)
    templates_dir = ensure_user_templates_dir()

    yaml_path = templates_dir / f"{safe_name}.yaml"
    jinja_path = templates_dir / f"{safe_name}.md.j2"

    try:
        # Validate YAML before saving
        yaml.safe_load(yaml_content)
        yaml_path.write_text(yaml_content)

        if jinja_content:
            # Validate Jinja2 syntax before saving
            env = _create_sandbox_env()
            env.from_string(jinja_content)  # This will raise if invalid
            jinja_path.write_text(jinja_content)

        return True
    except (yaml.YAMLError, TemplateError, OSError) as e:
        logger.error(f"Failed to save template {name}: {e}")
        return False


def delete_user_template(name: str) -> bool:
    """Delete a user template.

    Args:
        name: Template name

    Returns:
        True if deleted successfully
    """
    safe_name = _sanitize_template_name(name)

    yaml_path = USER_TEMPLATES_DIR / f"{safe_name}.yaml"
    jinja_path = USER_TEMPLATES_DIR / f"{safe_name}.md.j2"

    deleted = False

    if yaml_path.exists():
        yaml_path.unlink()
        deleted = True

    if jinja_path.exists():
        jinja_path.unlink()
        deleted = True

    return deleted
