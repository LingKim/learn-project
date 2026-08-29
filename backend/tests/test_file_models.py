from xuemian_ai.file_management.models import (
    FileAsset,
    FileAuditEvent,
    FileCleanupTask,
    FileOrphanCandidate,
    FilePolicyVersion,
    KnowledgeBaseFile,
    StoredObject,
    UploadSession,
)


def test_file_models_compose_only_required_common_fields() -> None:
    upload_columns = set(UploadSession.__table__.columns.keys())
    asset_columns = set(FileAsset.__table__.columns.keys())
    audit_columns = set(FileAuditEvent.__table__.columns.keys())

    assert {"created_at", "updated_at"} <= upload_columns
    assert "deleted_at" not in upload_columns
    assert {"created_by", "updated_by", "deleted_at", "deleted_by"} <= set(asset_columns)
    assert "updated_at" not in audit_columns
    assert "occurred_at" in audit_columns


def test_file_models_expose_identity_and_state_constraints() -> None:
    policy_indexes = {index.name for index in FilePolicyVersion.__table__.indexes}
    binding_indexes = {index.name for index in KnowledgeBaseFile.__table__.indexes}
    stored_unique = {
        tuple(column.name for column in constraint.columns)
        for constraint in StoredObject.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    task_unique = {
        tuple(column.name for column in constraint.columns)
        for constraint in FileCleanupTask.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert "uq_file_policy_versions_published" in policy_indexes
    assert "uq_knowledge_base_files_active_asset" in binding_indexes
    assert ("storage_domain", "sha256", "byte_size") in stored_unique
    assert ("idempotency_key",) in task_unique
    assert FileOrphanCandidate.__tablename__ == "file_orphan_candidates"
