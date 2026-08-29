import io
import zipfile

import pytest
from pypdf import PdfWriter

from xuemian_ai.core.errors import PayloadTooLargeError, ValidationAppError
from xuemian_ai.file_management.policy import DEFAULT_RULES
from xuemian_ai.file_management.validation import (
    normalize_digest,
    normalize_filename,
    validate_content,
    validate_declared_file,
)


def _knowledge_rules() -> dict[str, object]:
    value = DEFAULT_RULES["knowledge_document"]
    assert isinstance(value, dict)
    return value


def _docx(document_xml: bytes, *, macro: bool = False) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types />")
        archive.writestr("word/document.xml", document_xml)
        if macro:
            archive.writestr("word/vbaProject.bin", b"macro")
    return output.getvalue()


def _pdf(*, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if encrypted:
        writer.encrypt("secret")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_filename_and_digests_are_normalized() -> None:
    assert normalize_filename(" ../\u0065\u0301.txt ") == "\u00e9.txt"
    assert normalize_digest("A" * 64, "sha256") == "a" * 64
    assert normalize_digest("B" * 32, "md5") == "b" * 32


@pytest.mark.parametrize("filename", ["..", "\x00", "a" * 256 + ".txt"])
def test_invalid_filename_is_rejected(filename: str) -> None:
    with pytest.raises(ValidationAppError) as exc_info:
        normalize_filename(filename)
    assert exc_info.value.error_key == "FILE_NAME_INVALID"


def test_declared_extension_and_size_are_enforced() -> None:
    rules = _knowledge_rules()
    with pytest.raises(ValidationAppError) as type_error:
        validate_declared_file("payload.exe", 10, rules)
    assert type_error.value.error_key == "FILE_TYPE_NOT_ALLOWED"

    with pytest.raises(PayloadTooLargeError) as size_error:
        validate_declared_file("large.pdf", 51 * 1024 * 1024, rules)
    assert size_error.value.error_key == "FILE_TOO_LARGE"


@pytest.mark.parametrize(
    ("filename", "content", "mime"),
    [
        ("notes.txt", "\ufeff面试笔记".encode(), "text/plain"),
        ("notes.md", b"# Interview", "text/markdown"),
    ],
)
def test_utf8_text_types_are_accepted(filename: str, content: bytes, mime: str) -> None:
    result = validate_content(filename, content, _knowledge_rules())
    assert result.detected_mime == mime
    assert result.character_count


def test_binary_or_non_utf8_text_is_rejected() -> None:
    rules = _knowledge_rules()
    with pytest.raises(ValidationAppError) as nul_error:
        validate_content("notes.txt", b"hello\x00world", rules)
    assert nul_error.value.error_key == "FILE_STRUCTURE_INVALID"

    with pytest.raises(ValidationAppError) as encoding_error:
        validate_content("notes.txt", b"\xff\xfe", rules)
    assert encoding_error.value.error_key == "FILE_ENCODING_INVALID"


def test_pdf_structure_encryption_and_extension_spoofing() -> None:
    rules = _knowledge_rules()
    assert validate_content("resume.pdf", _pdf(), rules).page_count == 1

    with pytest.raises(ValidationAppError) as encrypted_error:
        validate_content("resume.pdf", _pdf(encrypted=True), rules)
    assert encrypted_error.value.error_key == "FILE_ENCRYPTED"

    with pytest.raises(ValidationAppError) as spoof_error:
        validate_content("resume.pdf", b"not-a-pdf", rules)
    assert spoof_error.value.error_key == "FILE_TYPE_MISMATCH"


def test_docx_structure_and_macro_are_checked() -> None:
    rules = _knowledge_rules()
    document = (
        b'<w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>'
        b"Interview"
        b"</w:t></w:r></w:p></w:body></w:document>"
    )
    result = validate_content("notes.docx", _docx(document), rules)
    assert result.character_count == 9
    assert result.paragraph_count == 1

    with pytest.raises(ValidationAppError) as macro_error:
        validate_content("notes.docx", _docx(document, macro=True), rules)
    assert macro_error.value.error_key == "FILE_MACRO_NOT_ALLOWED"
