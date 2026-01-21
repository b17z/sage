"""Sage: Research orchestration layer for Agent Skills."""

__version__ = "1.1.0"

# Branded types for type-safe IDs
from sage.types import CheckpointId, KnowledgeId, SkillName, TaskId, TemplateName

__all__ = [
    "__version__",
    "CheckpointId",
    "KnowledgeId",
    "TaskId",
    "SkillName",
    "TemplateName",
]
