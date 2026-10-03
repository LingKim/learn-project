import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from xuemian_ai.accounts.models import User
from xuemian_ai.ai_quality.crypto import SnapshotCipher
from xuemian_ai.ai_quality.policy import check_version, transition_allowed, validate_text
from xuemian_ai.ai_quality.schemas import CaseCreate, TransitionRequest
from xuemian_ai.ai_quality.service import QualityService
from xuemian_ai.core.errors import (
    ConflictError,
    ForbiddenError,
    UpstreamServiceError,
    ValidationAppError,
)


def settings(keys, active="v1"):
    return SimpleNamespace(
        diagnostic_snapshot_keys=SecretStr(json.dumps(keys)),
        diagnostic_snapshot_active_key_id=active,
    )


def test_explicit_key_ring_encryption_rotation_and_scope_fencing():
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    scope = "grant:synthetic-case:synthetic-grant"
    cipher = SnapshotCipher(settings({"v1": old}))
    key_id, encrypted = cipher.encrypt(scope, {"query": "合成测试正文，不是用户资料"})
    assert "合成" not in encrypted
    rotated = SnapshotCipher(settings({"v1": old, "v2": new}, "v2"))
    assert rotated.decrypt(scope, key_id, encrypted) == {"query": "合成测试正文，不是用户资料"}
    assert rotated.encrypt(scope, {"query": "new"})[0] == "v2"
    for other_scope, other_key, token in [
        ("grant:other-case:synthetic-grant", key_id, encrypted),
        (scope, "missing", encrypted),
        (scope, key_id, encrypted[:-5] + "wrong"),
    ]:
        with pytest.raises(UpstreamServiceError) as raised:
            rotated.decrypt(other_scope, other_key, token)
        assert raised.value.error_key == "DIAGNOSTIC_CRYPTO_UNAVAILABLE"


@pytest.mark.parametrize(
    "keys,active",
    [({}, "v1"), ({"v1": "bad"}, "v1"), ({"v1": Fernet.generate_key().decode()}, "missing")],
)
def test_missing_or_invalid_keys_never_fall_back_to_plaintext(keys, active):
    with pytest.raises(UpstreamServiceError) as raised:
        SnapshotCipher(settings(keys, active))
    assert raised.value.status_code.value == 503


def test_explicit_consent_required_and_resolution_requires_public_reason():
    data = dict(
        source_id=uuid4(),
        trace_id=uuid4(),
        request_key=uuid4(),
        category="other",
        description="合成意见",
    )
    for consent in [None, False]:
        with pytest.raises(ValidationError):
            CaseCreate(**data, basic_access_confirmed=consent)
    assert CaseCreate(**data, basic_access_confirmed=True).basic_access_confirmed
    with pytest.raises(ValidationError):
        TransitionRequest(expected_version=1, status="resolved")
    with pytest.raises(ValidationError):
        CaseCreate(**data, basic_access_confirmed=True, password="unexpected")


@pytest.mark.parametrize(
    "text",
    [
        "<script>alert(1)</script>",
        "javascript:bad",
        "-----BEGIN PRIVATE KEY-----",
        "AKIAABCDEFGHIJKLMNOP",
    ],
)
def test_recognizable_script_and_credential_payloads_are_rejected(text):
    with pytest.raises(ValidationAppError) as raised:
        validate_text(text)
    assert text not in raised.value.message


def test_state_and_version_conflicts_do_not_override_prior_state():
    transition_allowed("triaging", "investigating")
    for state, target in [
        ("closed", "investigating"),
        ("submitted", "resolved"),
        ("resolved", "triaging"),
    ]:
        with pytest.raises(ConflictError):
            transition_allowed(state, target)
    with pytest.raises(ConflictError):
        check_version(3, 2)


def test_role_rejection_is_independent_of_resource_lookup():
    domain = QualityService(None, User(id=uuid4(), role="user"), None)
    with pytest.raises(ForbiddenError):
        domain._role(True)
    admin = QualityService(None, User(id=uuid4(), role="admin"), None)
    with pytest.raises(ForbiddenError):
        admin._role(False)
