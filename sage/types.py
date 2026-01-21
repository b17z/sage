"""Branded types for Sage.

NewType creates distinct types at the type-checking level while being
transparent at runtime. This catches bugs like passing a KnowledgeId
where a CheckpointId is expected.

Usage:
    from sage.types import CheckpointId, KnowledgeId

    def save_checkpoint(cp_id: CheckpointId) -> None: ...
    def load_knowledge(k_id: KnowledgeId) -> None: ...

    # Type checker catches this mistake:
    save_checkpoint(KnowledgeId("jwt-auth"))  # Error!
"""

from typing import NewType

# Checkpoint identifiers (e.g., "2026-01-21_jwt-authentication")
CheckpointId = NewType("CheckpointId", str)

# Knowledge item identifiers (e.g., "jwt-auth-patterns")
KnowledgeId = NewType("KnowledgeId", str)

# Task identifiers (e.g., "task_20260121_143052_a1b2c3d4")
TaskId = NewType("TaskId", str)

# Skill names (e.g., "crypto-payments")
SkillName = NewType("SkillName", str)

# Template names (e.g., "research", "decision")
TemplateName = NewType("TemplateName", str)
