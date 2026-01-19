"""Tests for sage.templates module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sage.templates import (
    CheckpointTemplate,
    TemplateField,
    ValidationResult,
    _create_sandbox_env,
    _parse_template_yaml,
    _render_default_markdown,
    _sanitize_template_name,
    get_default_template,
    list_templates,
    load_template,
    render_checkpoint,
    validate_checkpoint_data,
)


class TestTemplateSanitization:
    """Tests for template name sanitization."""

    def test_sanitize_normal_name(self):
        """Normal names are unchanged."""
        assert _sanitize_template_name("default") == "default"
        assert _sanitize_template_name("code-review") == "code-review"
        assert _sanitize_template_name("my_template") == "my_template"

    def test_sanitize_path_traversal(self):
        """Path traversal attempts are sanitized."""
        assert ".." not in _sanitize_template_name("../../../etc/passwd")
        assert "/" not in _sanitize_template_name("../../secret")
        assert _sanitize_template_name("../evil") == "evil"

    def test_sanitize_special_chars(self):
        """Special characters are replaced."""
        assert _sanitize_template_name("my template!") == "my-template"
        assert _sanitize_template_name("test@123") == "test-123"

    def test_sanitize_empty_returns_default(self):
        """Empty string returns 'default'."""
        assert _sanitize_template_name("") == "default"
        assert _sanitize_template_name("   ") == "default"


class TestTemplateLoading:
    """Tests for template loading."""

    def test_load_default_template(self):
        """Default template loads successfully."""
        template = load_template("default")

        assert template is not None
        assert template.name == "default"
        assert len(template.fields) > 0

    def test_load_research_template(self):
        """Research template loads successfully."""
        template = load_template("research")

        assert template is not None
        assert template.name == "research"

    def test_load_decision_template(self):
        """Decision template loads successfully."""
        template = load_template("decision")

        assert template is not None
        assert template.name == "decision"

    def test_load_code_review_template(self):
        """Code-review template loads successfully."""
        template = load_template("code-review")

        assert template is not None
        assert template.name == "code-review"

    def test_load_nonexistent_template(self):
        """Nonexistent template returns None."""
        template = load_template("nonexistent-template-xyz")

        assert template is None

    def test_list_templates_includes_builtins(self):
        """list_templates includes built-in templates."""
        templates = list_templates()

        assert "default" in templates
        assert "research" in templates
        assert "decision" in templates
        assert "code-review" in templates


class TestGetDefaultTemplate:
    """Tests for get_default_template."""

    def test_get_default_template(self):
        """get_default_template returns a valid template."""
        template = get_default_template()

        assert template is not None
        assert template.name == "default"

        # Check required fields
        field_names = {f.name for f in template.fields}
        assert "core_question" in field_names
        assert "thesis" in field_names
        assert "confidence" in field_names


class TestTemplateValidation:
    """Tests for checkpoint data validation."""

    def test_validate_with_required_fields(self):
        """Validation passes with all required fields."""
        template = CheckpointTemplate(
            name="test",
            fields=(
                TemplateField(name="thesis", required=True),
                TemplateField(name="confidence", required=True),
            ),
        )

        data = {"thesis": "Test thesis", "confidence": 0.8}
        result = validate_checkpoint_data(data, template)

        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_missing_required_field(self):
        """Validation fails when required field is missing."""
        template = CheckpointTemplate(
            name="test",
            fields=(
                TemplateField(name="thesis", required=True),
                TemplateField(name="confidence", required=True),
            ),
        )

        data = {"thesis": "Test thesis"}  # missing confidence
        result = validate_checkpoint_data(data, template)

        assert result.valid is False
        assert any("confidence" in e for e in result.errors)

    def test_validate_empty_required_field(self):
        """Validation fails when required field is empty."""
        template = CheckpointTemplate(
            name="test",
            fields=(TemplateField(name="thesis", required=True),),
        )

        data = {"thesis": ""}
        result = validate_checkpoint_data(data, template)

        assert result.valid is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_validate_unknown_fields_warning(self):
        """Unknown fields produce warnings, not errors."""
        template = CheckpointTemplate(
            name="test",
            fields=(TemplateField(name="thesis", required=True),),
        )

        data = {"thesis": "Test", "unknown_field": "value"}
        result = validate_checkpoint_data(data, template)

        assert result.valid is True
        assert any("unknown_field" in w for w in result.warnings)


class TestTemplateRendering:
    """Tests for checkpoint rendering."""

    def test_render_default_markdown(self):
        """Default markdown rendering works."""
        template = get_default_template()
        data = {
            "id": "test-id",
            "ts": "2026-01-20T10:00:00",
            "trigger": "manual",
            "core_question": "What should we decide?",
            "thesis": "We should do X.",
            "confidence": 0.85,
        }

        rendered = _render_default_markdown(data, template)

        assert "---" in rendered  # YAML frontmatter
        assert "test-id" in rendered
        assert "What should we decide?" in rendered
        assert "We should do X." in rendered
        assert "0.85" in rendered

    def test_render_with_key_evidence(self):
        """Rendering includes key evidence list."""
        template = get_default_template()
        data = {
            "id": "test-id",
            "ts": "2026-01-20T10:00:00",
            "core_question": "Test",
            "thesis": "Test",
            "confidence": 0.8,
            "key_evidence": ["Evidence 1", "Evidence 2"],
        }

        rendered = _render_default_markdown(data, template)

        assert "Evidence 1" in rendered
        assert "Evidence 2" in rendered
        assert "## Key Evidence" in rendered

    def test_render_with_sources(self):
        """Rendering includes sources."""
        template = get_default_template()
        data = {
            "id": "test-id",
            "ts": "2026-01-20T10:00:00",
            "core_question": "Test",
            "thesis": "Test",
            "confidence": 0.8,
            "sources": [
                {"id": "doc1", "type": "document", "take": "Key insight", "relation": "supports"}
            ],
        }

        rendered = _render_default_markdown(data, template)

        assert "doc1" in rendered
        assert "document" in rendered
        assert "Key insight" in rendered
        assert "## Sources" in rendered


class TestJinjaEnvironment:
    """Tests for Jinja2 sandboxing."""

    def test_sandbox_env_created(self):
        """Sandbox environment is created successfully."""
        env = _create_sandbox_env()

        assert env is not None
        # Test basic template
        template = env.from_string("Hello {{ name }}")
        result = template.render(name="World")
        assert result == "Hello World"

    def test_sandbox_blocks_dangerous_operations(self):
        """Sandbox blocks dangerous operations."""
        env = _create_sandbox_env()

        # This should fail - accessing system modules
        dangerous_templates = [
            "{{ ''.__class__.__mro__[2].__subclasses__() }}",
        ]

        for template_str in dangerous_templates:
            with pytest.raises(Exception):
                template = env.from_string(template_str)
                template.render()


class TestTemplateYamlParsing:
    """Tests for YAML template parsing."""

    def test_parse_simple_yaml(self):
        """Simple YAML template is parsed correctly."""
        data = {
            "name": "test",
            "description": "Test template",
            "fields": [
                {"name": "thesis", "required": True},
                {"name": "confidence", "required": True},
                {"name": "notes"},
            ],
        }

        template = _parse_template_yaml(data)

        assert template.name == "test"
        assert template.description == "Test template"
        assert len(template.fields) == 3

    def test_parse_string_fields(self):
        """Fields can be simple strings."""
        data = {
            "name": "test",
            "fields": ["thesis", "confidence", "notes"],
        }

        template = _parse_template_yaml(data)

        assert len(template.fields) == 3
        assert template.fields[0].name == "thesis"

    def test_parse_with_jinja_template(self):
        """Jinja template is included when provided."""
        data = {
            "name": "test",
            "fields": [{"name": "thesis", "required": True}],
        }
        jinja = "# {{ core_question }}\n\n{{ thesis }}"

        template = _parse_template_yaml(data, jinja)

        assert template.jinja_template == jinja


class TestRenderCheckpoint:
    """Tests for render_checkpoint function."""

    def test_render_with_default_template(self):
        """render_checkpoint uses default renderer when no Jinja template."""
        template = CheckpointTemplate(
            name="test",
            fields=(TemplateField(name="thesis", required=True),),
            jinja_template=None,
        )
        data = {
            "id": "test-id",
            "ts": "2026-01-20T10:00:00",
            "thesis": "Test thesis",
            "confidence": 0.8,
        }

        rendered = render_checkpoint(data, template)

        assert "Test thesis" in rendered
        assert "---" in rendered  # Has frontmatter

    def test_render_with_jinja_template(self):
        """render_checkpoint uses Jinja template when provided."""
        template = CheckpointTemplate(
            name="custom",
            fields=(TemplateField(name="thesis", required=True),),
            jinja_template="THESIS: {{ thesis }}\nCONFIDENCE: {{ confidence }}%",
        )
        data = {
            "thesis": "Custom thesis",
            "confidence": 0.85,
        }

        rendered = render_checkpoint(data, template)

        assert "THESIS: Custom thesis" in rendered
        assert "CONFIDENCE: 0.85%" in rendered


class TestUserTemplates:
    """Tests for user template management."""

    def test_user_templates_override_builtin(self, tmp_path: Path):
        """User templates override built-in templates."""
        # Create a user template that overrides 'default'
        user_templates = tmp_path / "templates"
        user_templates.mkdir()

        custom_yaml = """
name: default
description: Custom default template
fields:
  - name: custom_field
    required: true
"""
        (user_templates / "default.yaml").write_text(custom_yaml)

        # Patch the directories
        with patch("sage.templates._get_templates_dirs", return_value=[user_templates]):
            template = load_template("default")

            assert template is not None
            assert template.description == "Custom default template"
            assert any(f.name == "custom_field" for f in template.fields)
