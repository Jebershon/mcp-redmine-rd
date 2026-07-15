"""Unit tests for attachment image preparation."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from mcp_redmine_rd.images import (
    MAX_DIMENSION,
    ImageProcessingError,
    downscale,
    is_image,
    select_images,
)


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


# --- is_image ---


def test_is_image_png():
    assert is_image({"content_type": "image/png"})


def test_is_image_with_charset_suffix():
    assert is_image({"content_type": "image/jpeg; charset=binary"})


def test_is_image_rejects_pdf():
    assert not is_image({"content_type": "application/pdf"})


def test_is_image_missing_content_type():
    assert not is_image({"filename": "screenshot.png"})


# --- downscale ---


def test_downscale_shrinks_oversized_image():
    result = downscale(_png(4000, 3000))
    with Image.open(io.BytesIO(result)) as img:
        assert max(img.size) == MAX_DIMENSION
        assert img.size == (MAX_DIMENSION, 1125)  # aspect ratio preserved


def test_downscale_leaves_small_image_dimensions_alone():
    result = downscale(_png(800, 600))
    with Image.open(io.BytesIO(result)) as img:
        assert img.size == (800, 600)


def test_downscale_always_outputs_png():
    buffer = io.BytesIO()
    Image.new("RGB", (100, 100), color="blue").save(buffer, format="JPEG")
    result = downscale(buffer.getvalue())
    with Image.open(io.BytesIO(result)) as img:
        assert img.format == "PNG"


def test_downscale_rejects_non_image_bytes():
    with pytest.raises(ImageProcessingError):
        downscale(b"this is not an image")


# --- select_images ---


def _attachment(aid: int, content_type: str = "image/png") -> dict:
    return {"id": aid, "content_type": content_type, "filename": f"{aid}.png"}


def test_select_images_filters_non_images():
    attachments = [
        _attachment(1),
        _attachment(2, "application/pdf"),
        _attachment(3),
    ]
    inline, skipped = select_images(attachments)
    assert [a["id"] for a in inline] == [1, 3]
    assert skipped == []


def test_select_images_under_limit_returns_all():
    attachments = [_attachment(i) for i in range(3)]
    inline, skipped = select_images(attachments, limit=4)
    assert len(inline) == 3
    assert skipped == []


def test_select_images_keeps_newest_when_over_limit():
    """Redmine returns attachments oldest-first; the latest screenshots win."""
    attachments = [_attachment(i) for i in range(6)]
    inline, skipped = select_images(attachments, limit=2)
    assert [a["id"] for a in inline] == [4, 5]
    assert [a["id"] for a in skipped] == [0, 1, 2, 3]
