from xuemian_ai.main import create_app


def test_openapi_exposes_file_upload_management_and_policy_endpoints() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]

    assert "/api/v1/knowledge-bases/{knowledge_base_id}/file-upload-sessions" in paths
    assert "/api/v1/file-upload-sessions/{session_id}/complete" in paths
    assert "/api/v1/knowledge-bases/{knowledge_base_id}/files/{knowledge_file_id}" in paths
    assert "/api/v1/file-policies/effective" in paths
    assert "/api/v1/admin/file-policy-versions/{policy_id}/publish" in paths


def test_file_contract_keeps_storage_internals_out_of_public_schemas() -> None:
    schema = create_app().openapi()
    schemas = schema["components"]["schemas"]
    forbidden = {"bucket", "object_key", "reference_count", "stored_object_id"}

    for name in ("UploadPlan", "UploadSessionView", "KnowledgeFileView", "DownloadUrlView"):
        assert forbidden.isdisjoint(schemas[name].get("properties", {}))


def test_upload_creation_requires_idempotency_header() -> None:
    operation = create_app().openapi()["paths"][
        "/api/v1/knowledge-bases/{knowledge_base_id}/file-upload-sessions"
    ]["post"]
    header = next(parameter for parameter in operation["parameters"] if parameter["in"] == "header")

    assert header["name"] == "Idempotency-Key"
    assert header["required"] is True
