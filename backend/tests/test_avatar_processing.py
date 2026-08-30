from io import BytesIO

import pytest
from PIL import Image

from xuemian_ai.core.errors import ValidationAppError
from xuemian_ai.profiles.image_processing import process_avatar_image


def _image_bytes(format_name: str, size: tuple[int, int] = (800, 400)) -> bytes:
    output = BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "private metadata"
    Image.new("RGB", size, (230, 180, 90)).save(
        output,
        format=format_name,
        exif=exif,
    )
    return output.getvalue()


@pytest.mark.parametrize("format_name", ["JPEG", "PNG", "WEBP"])
def test_avatar_processing_outputs_square_static_webp_without_exif(format_name: str) -> None:
    result = process_avatar_image(_image_bytes(format_name))

    with Image.open(BytesIO(result.content)) as image:
        assert image.format == "WEBP"
        assert image.size == (512, 512)
        assert getattr(image, "n_frames", 1) == 1
        assert not image.getexif()
    expected_source_mime = "image/jpeg" if format_name == "JPEG" else f"image/{format_name.lower()}"
    assert result.source_mime == expected_source_mime


def test_avatar_processing_rejects_animation() -> None:
    output = BytesIO()
    frames = [Image.new("RGB", (32, 32), color) for color in ("red", "blue")]
    frames[0].save(output, format="WEBP", save_all=True, append_images=frames[1:], loop=0)

    with pytest.raises(ValidationAppError) as captured:
        process_avatar_image(output.getvalue())

    assert captured.value.error_key == "AVATAR_ANIMATED_IMAGE"


def test_avatar_processing_rejects_dimension_limit() -> None:
    with pytest.raises(ValidationAppError) as captured:
        process_avatar_image(_image_bytes("PNG", (8193, 1)))

    assert captured.value.error_key == "AVATAR_IMAGE_LIMIT"
