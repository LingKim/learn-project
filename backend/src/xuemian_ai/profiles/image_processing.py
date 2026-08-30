from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from xuemian_ai.core.errors import ValidationAppError

_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
_MAX_DIMENSION = 8192
_MAX_PIXELS = 40_000_000


@dataclass(frozen=True, slots=True)
class ProcessedAvatar:
    content: bytes
    source_mime: str
    width: int
    height: int


def process_avatar_image(content: bytes) -> ProcessedAvatar:
    try:
        with Image.open(BytesIO(content)) as source:
            source_format = source.format
            if source_format not in _ALLOWED_FORMATS:
                raise ValidationAppError("头像图片格式不支持", error_key="AVATAR_INVALID_IMAGE")
            if getattr(source, "n_frames", 1) != 1 or bool(getattr(source, "is_animated", False)):
                raise ValidationAppError("头像不能使用动画图片", error_key="AVATAR_ANIMATED_IMAGE")
            width, height = source.size
            if (
                width <= 0
                or height <= 0
                or max(width, height) > _MAX_DIMENSION
                or width * height > _MAX_PIXELS
            ):
                raise ValidationAppError("头像图片尺寸超过限制", error_key="AVATAR_IMAGE_LIMIT")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            converted = oriented.convert("RGB")
            side = min(converted.size)
            left = (converted.width - side) // 2
            top = (converted.height - side) // 2
            cropped = converted.crop((left, top, left + side, top + side))
            resized = cropped.resize((512, 512), Image.Resampling.LANCZOS)
            output = BytesIO()
            resized.save(output, format="WEBP", quality=88, method=6, exif=b"")
            source_mime = (
                "image/jpeg" if source_format == "JPEG" else f"image/{source_format.lower()}"
            )
            return ProcessedAvatar(
                content=output.getvalue(),
                source_mime=source_mime,
                width=512,
                height=512,
            )
    except ValidationAppError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationAppError("头像不是有效图片", error_key="AVATAR_INVALID_IMAGE") from exc
