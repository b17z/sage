"""Tests for branded types."""

import pytest

from sage.types import CheckpointId, KnowledgeId, SkillName, TaskId, TemplateName


class TestBrandedTypesBasics:
    """Test that branded types work as string wrappers."""

    def test_checkpoint_id_is_string(self):
        """CheckpointId wraps string values."""
        cp_id = CheckpointId("2026-01-22_jwt-auth")
        assert cp_id == "2026-01-22_jwt-auth"
        assert isinstance(cp_id, str)

    def test_knowledge_id_is_string(self):
        """KnowledgeId wraps string values."""
        k_id = KnowledgeId("jwt-auth-patterns")
        assert k_id == "jwt-auth-patterns"
        assert isinstance(k_id, str)

    def test_task_id_is_string(self):
        """TaskId wraps string values."""
        t_id = TaskId("task_20260122_143052_a1b2c3d4")
        assert t_id == "task_20260122_143052_a1b2c3d4"
        assert isinstance(t_id, str)

    def test_skill_name_is_string(self):
        """SkillName wraps string values."""
        s_name = SkillName("crypto-payments")
        assert s_name == "crypto-payments"
        assert isinstance(s_name, str)

    def test_template_name_is_string(self):
        """TemplateName wraps string values."""
        t_name = TemplateName("research")
        assert t_name == "research"
        assert isinstance(t_name, str)


class TestBrandedTypesStringOperations:
    """Test that branded types support string operations."""

    def test_checkpoint_id_string_methods(self):
        """CheckpointId supports string methods."""
        cp_id = CheckpointId("2026-01-22_jwt-auth")
        assert cp_id.startswith("2026")
        assert cp_id.endswith("auth")
        assert "jwt" in cp_id
        assert cp_id.split("_") == ["2026-01-22", "jwt-auth"]

    def test_knowledge_id_string_methods(self):
        """KnowledgeId supports string methods."""
        k_id = KnowledgeId("jwt-auth-patterns")
        assert k_id.replace("-", "_") == "jwt_auth_patterns"
        assert k_id.upper() == "JWT-AUTH-PATTERNS"
        assert len(k_id) == 17

    def test_task_id_string_methods(self):
        """TaskId supports string methods."""
        t_id = TaskId("task_20260122_143052_a1b2c3d4")
        parts = t_id.split("_")
        assert parts[0] == "task"
        assert parts[1] == "20260122"
        assert parts[2] == "143052"

    def test_skill_name_validation_pattern(self):
        """SkillName can be validated with regex."""
        import re

        s_name = SkillName("crypto-payments")
        # kebab-case pattern
        assert re.match(r"^[a-z][a-z0-9-]*$", s_name)

    def test_template_name_validation(self):
        """TemplateName can be validated."""
        t_name = TemplateName("code-review")
        assert t_name in ["default", "research", "decision", "code-review"]


class TestBrandedTypesEquality:
    """Test equality comparisons for branded types."""

    def test_checkpoint_ids_equal(self):
        """Equal CheckpointIds compare equal."""
        id1 = CheckpointId("test-id")
        id2 = CheckpointId("test-id")
        assert id1 == id2

    def test_checkpoint_id_equals_string(self):
        """CheckpointId equals equivalent string."""
        cp_id = CheckpointId("test-id")
        assert cp_id == "test-id"
        assert "test-id" == cp_id

    def test_different_type_ids_equal_if_same_string(self):
        """Different branded types with same string compare equal (runtime behavior)."""
        # At runtime, NewType is transparent - these are just strings
        cp_id = CheckpointId("same-value")
        k_id = KnowledgeId("same-value")
        # This is expected runtime behavior - type checking catches misuse at static analysis time
        assert cp_id == k_id

    def test_knowledge_ids_not_equal_different_values(self):
        """Different KnowledgeIds are not equal."""
        id1 = KnowledgeId("id-one")
        id2 = KnowledgeId("id-two")
        assert id1 != id2


class TestBrandedTypesHashable:
    """Test that branded types can be used in sets and as dict keys."""

    def test_checkpoint_id_hashable(self):
        """CheckpointId can be used in sets."""
        ids = {CheckpointId("id1"), CheckpointId("id2"), CheckpointId("id1")}
        assert len(ids) == 2

    def test_knowledge_id_as_dict_key(self):
        """KnowledgeId can be used as dict key."""
        data = {
            KnowledgeId("jwt-patterns"): "JWT knowledge",
            KnowledgeId("oauth-patterns"): "OAuth knowledge",
        }
        assert data[KnowledgeId("jwt-patterns")] == "JWT knowledge"
        assert data["jwt-patterns"] == "JWT knowledge"  # String key also works

    def test_task_id_in_set(self):
        """TaskId can be added to and checked in sets."""
        task_ids = set()
        t_id = TaskId("task_123")
        task_ids.add(t_id)
        assert t_id in task_ids
        assert "task_123" in task_ids


class TestBrandedTypesUsageInModules:
    """Test that branded types are used correctly in Sage modules."""

    def test_checkpoint_uses_checkpoint_id(self):
        """Checkpoint module uses CheckpointId."""
        from sage.checkpoint import generate_checkpoint_id

        cp_id = generate_checkpoint_id("test description")
        # Should be a string (CheckpointId is transparent at runtime)
        assert isinstance(cp_id, str)
        # Should follow expected format
        assert "_" in cp_id  # date_description format

    def test_tasks_uses_task_id(self):
        """Tasks module uses TaskId."""
        from sage.tasks import generate_task_id

        t_id = generate_task_id()
        assert isinstance(t_id, str)
        assert t_id.startswith("task_")

    def test_knowledge_item_uses_knowledge_id(self):
        """KnowledgeItem uses KnowledgeId for its id field."""
        from sage.knowledge import (
            KnowledgeItem,
            KnowledgeMetadata,
            KnowledgeScope,
            KnowledgeTriggers,
        )

        item = KnowledgeItem(
            id=KnowledgeId("test-id"),
            file="test.md",
            triggers=KnowledgeTriggers(keywords=("test",)),
            scope=KnowledgeScope(),
            metadata=KnowledgeMetadata(added="2026-01-22", source="test"),
        )
        assert item.id == "test-id"
        assert isinstance(item.id, str)


class TestBrandedTypesExports:
    """Test that branded types are properly exported from sage package."""

    def test_types_exported_from_sage(self):
        """Branded types are exported from main sage package."""
        import sage

        assert hasattr(sage, "CheckpointId")
        assert hasattr(sage, "KnowledgeId")
        assert hasattr(sage, "TaskId")
        assert hasattr(sage, "SkillName")
        assert hasattr(sage, "TemplateName")

    def test_types_in_all(self):
        """Branded types are in __all__."""
        import sage

        assert "CheckpointId" in sage.__all__
        assert "KnowledgeId" in sage.__all__
        assert "TaskId" in sage.__all__
        assert "SkillName" in sage.__all__
        assert "TemplateName" in sage.__all__

    def test_can_import_directly(self):
        """Can import types directly from sage."""
        from sage import CheckpointId, KnowledgeId, SkillName, TaskId, TemplateName

        # All should be callable (NewType returns the constructor)
        assert callable(CheckpointId)
        assert callable(KnowledgeId)
        assert callable(TaskId)
        assert callable(SkillName)
        assert callable(TemplateName)


class TestBrandedTypesDocumentation:
    """Test that types module is properly documented."""

    def test_module_has_docstring(self):
        """Types module has documentation."""
        import sage.types

        assert sage.types.__doc__ is not None
        assert "Branded types" in sage.types.__doc__

    def test_docstring_shows_usage(self):
        """Types module docstring shows usage example."""
        import sage.types

        assert "CheckpointId" in sage.types.__doc__
        assert "KnowledgeId" in sage.types.__doc__
