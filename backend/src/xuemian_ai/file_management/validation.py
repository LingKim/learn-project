import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePath
from typing import cast
from xml.etree import ElementTree

from pypdf import PdfReader

from xuemian_ai.core.errors import PayloadTooLargeError, ValidationAppError

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_MD5_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _rule_int(rules: dict[str, object], key: str) -> int:
    value = rules[key]
    if not isinstance(value, int):
        raise ValidationAppError("文件策略结构不合法", error_key="FILE_POLICY_INVALID")
    return value


def _rule_strings(rules: dict[str, object], key: str) -> list[str]:
    value = rules[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValidationAppError("文件策略结构不合法", error_key="FILE_POLICY_INVALID")
    return cast(list[str], value)


@dataclass(frozen=True, slots=True)
class ValidationResult:
    detected_mime: str
    extension: str
    page_count: int | None = None
    character_count: int | None = None
    paragraph_count: int | None = None


def normalize_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFC", PurePath(value.strip()).name)
    normalized = _CONTROL_CHARACTERS.sub("", normalized).strip()
    if not normalized or normalized in {".", ".."}:
        raise ValidationAppError("文件名不能为空", error_key="FILE_NAME_INVALID")
    if len(normalized.encode("utf-8")) > 255:
        raise ValidationAppError("文件名不能超过 255 字节", error_key="FILE_NAME_INVALID")
    return normalized


def normalize_digest(value: str | None, kind: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    pattern = _SHA256_PATTERN if kind == "sha256" else _MD5_PATTERN
    if pattern.fullmatch(normalized) is None:
        raise ValidationAppError("文件摘要格式不合法", error_key="FILE_DIGEST_INVALID")
    return normalized


def validate_declared_file(filename: str, size: int, rules: dict[str, object]) -> str:
    normalized = normalize_filename(filename)
    if size <= 0:
        raise ValidationAppError("文件内容不能为空", error_key="FILE_EMPTY")
    max_bytes = _rule_int(rules, "max_bytes")
    if size > max_bytes:
        raise PayloadTooLargeError(error_key="FILE_TOO_LARGE")
    extension = PurePath(normalized).suffix.lower().lstrip(".")
    allowed = {value.lower() for value in _rule_strings(rules, "extensions")}
    if extension not in allowed:
        raise ValidationAppError("不支持该文件类型", error_key="FILE_TYPE_NOT_ALLOWED")
    return normalized


def validate_content(filename: str, content: bytes, rules: dict[str, object]) -> ValidationResult:
    extension = PurePath(filename).suffix.lower().lstrip(".")
    if len(content) > _rule_int(rules, "max_bytes"):
        raise PayloadTooLargeError(error_key="FILE_TOO_LARGE")
    if not content:
        raise ValidationAppError("文件内容不能为空", error_key="FILE_EMPTY")
    if extension == "pdf":
        return _validate_pdf(content, rules)
    if extension == "docx":
        return _validate_docx(content, rules)
    if extension in {"txt", "md"}:
        return _validate_text(content, extension, rules)
    raise ValidationAppError("不支持该文件类型", error_key="FILE_TYPE_NOT_ALLOWED")


def _validate_pdf(content: bytes, rules: dict[str, object]) -> ValidationResult:
    if not content.startswith(b"%PDF-"):
        raise ValidationAppError("文件真实类型与扩展名不一致", error_key="FILE_TYPE_MISMATCH")
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValidationAppError("暂不支持加密 PDF", error_key="FILE_ENCRYPTED")
        pages = len(reader.pages)
        if pages <= 0:
            raise ValidationAppError("PDF 不包含有效页面", error_key="FILE_STRUCTURE_INVALID")
        if pages > _rule_int(rules, "pdf_max_pages"):
            raise ValidationAppError("PDF 页数超过限制", error_key="FILE_PAGE_LIMIT_EXCEEDED")
        if reader.attachments:
            raise ValidationAppError("PDF 不得包含嵌入附件", error_key="FILE_EMBEDDED_ATTACHMENT")
    except ValidationAppError:
        raise
    except Exception as exc:
        raise ValidationAppError(
            "PDF 文件损坏或结构不合法", error_key="FILE_STRUCTURE_INVALID"
        ) from exc
    return ValidationResult(detected_mime="application/pdf", extension="pdf", page_count=pages)


def _validate_docx(content: bytes, rules: dict[str, object]) -> ValidationResult:
    if not content.startswith(b"PK"):
        raise ValidationAppError("文件真实类型与扩展名不一致", error_key="FILE_TYPE_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValidationAppError("DOCX 内部结构不合法", error_key="FILE_STRUCTURE_INVALID")
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise ValidationAppError(
                    "不支持带宏的 Office 文件", error_key="FILE_MACRO_NOT_ALLOWED"
                )
            total_uncompressed = sum(item.file_size for item in archive.infolist())
            if total_uncompressed > _rule_int(rules, "docx_max_uncompressed_bytes"):
                raise ValidationAppError("DOCX 解压后大小超过限制", error_key="FILE_ARCHIVE_LIMIT")
            compressed = max(1, sum(item.compress_size for item in archive.infolist()))
            if total_uncompressed / compressed > _rule_int(rules, "docx_max_compression_ratio"):
                raise ValidationAppError("DOCX 压缩比异常", error_key="FILE_ARCHIVE_LIMIT")
            xml = archive.read("word/document.xml")
    except ValidationAppError:
        raise
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise ValidationAppError(
            "DOCX 文件损坏或结构不合法", error_key="FILE_STRUCTURE_INVALID"
        ) from exc
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ValidationAppError("DOCX 正文结构不合法", error_key="FILE_STRUCTURE_INVALID") from exc
    texts = [element.text or "" for element in root.iter() if element.tag.endswith("}t")]
    characters = sum(len(value) for value in texts)
    paragraphs = sum(1 for element in root.iter() if element.tag.endswith("}p"))
    if characters <= 0:
        raise ValidationAppError("DOCX 不包含有效正文", error_key="FILE_EMPTY")
    if characters > _rule_int(rules, "text_max_characters"):
        raise ValidationAppError("DOCX 正文字符数超过限制", error_key="FILE_TEXT_LIMIT_EXCEEDED")
    if paragraphs > _rule_int(rules, "docx_max_paragraphs"):
        raise ValidationAppError("DOCX 段落数超过限制", error_key="FILE_PARAGRAPH_LIMIT_EXCEEDED")
    return ValidationResult(
        detected_mime=_DOCX_CONTENT_TYPE,
        extension="docx",
        character_count=characters,
        paragraph_count=paragraphs,
    )


def _validate_text(content: bytes, extension: str, rules: dict[str, object]) -> ValidationResult:
    if b"\x00" in content:
        raise ValidationAppError("文本文件包含非法二进制内容", error_key="FILE_STRUCTURE_INVALID")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationAppError(
            "文本文件必须使用 UTF-8 编码", error_key="FILE_ENCODING_INVALID"
        ) from exc
    if not text.strip():
        raise ValidationAppError("文本文件内容不能为空", error_key="FILE_EMPTY")
    if len(text) > _rule_int(rules, "text_max_characters"):
        raise ValidationAppError("文本字符数超过限制", error_key="FILE_TEXT_LIMIT_EXCEEDED")
    mime = "text/markdown" if extension == "md" else "text/plain"
    return ValidationResult(detected_mime=mime, extension=extension, character_count=len(text))
