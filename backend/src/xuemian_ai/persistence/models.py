"""集中导入当前真实模型，供 Alembic 发现元数据。"""

from xuemian_ai.accounts.models import AuthAuditEvent, AuthSession, User
from xuemian_ai.file_management.models import (
    FileAsset,
    FileAuditEvent,
    FileCleanupTask,
    FileDeletionTombstone,
    FileOrphanCandidate,
    FilePolicyVersion,
    KnowledgeBaseFile,
    StoredObject,
    UploadSession,
)
from xuemian_ai.knowledge_bases.models import KnowledgeBase

__all__ = [
    "AuthAuditEvent",
    "AuthSession",
    "FileAsset",
    "FileAuditEvent",
    "FileCleanupTask",
    "FileDeletionTombstone",
    "FileOrphanCandidate",
    "FilePolicyVersion",
    "KnowledgeBase",
    "KnowledgeBaseFile",
    "StoredObject",
    "UploadSession",
    "User",
]
