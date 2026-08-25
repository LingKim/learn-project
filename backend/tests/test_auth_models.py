from xuemian_ai.accounts.models import AuthAuditEvent, AuthSession, User
from xuemian_ai.knowledge_bases.models import KnowledgeBase


def test_common_fields_are_composed_by_model_semantics() -> None:
    user_columns = set(User.__table__.columns.keys())
    session_columns = set(AuthSession.__table__.columns.keys())
    audit_columns = set(AuthAuditEvent.__table__.columns.keys())
    knowledge_base_columns = set(KnowledgeBase.__table__.columns.keys())

    assert {
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "deleted_at",
        "deleted_by",
    } <= user_columns
    assert {"created_at", "updated_at"} <= session_columns
    assert "deleted_at" not in session_columns
    assert "occurred_at" in audit_columns
    assert {"created_at", "updated_at", "updated_by", "deleted_at"}.isdisjoint(audit_columns)
    assert {
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "deleted_at",
        "deleted_by",
    } <= knowledge_base_columns


def test_authentication_constraints_exist_in_metadata() -> None:
    user_constraint_names = {constraint.name for constraint in User.__table__.constraints}
    session_unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in AuthSession.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    knowledge_index_names = {index.name for index in KnowledgeBase.__table__.indexes}

    assert {"ck_users_role", "ck_users_status"} <= user_constraint_names
    assert ("current_refresh_jti",) in session_unique_columns
    assert ("current_refresh_digest",) in session_unique_columns
    assert "uq_knowledge_bases_active_default_owner" in knowledge_index_names
