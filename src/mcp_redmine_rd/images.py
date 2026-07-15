"""Preparation of Redmine attachments for MCP image content blocks.

Bug screenshots are routinely 2–5 MB at full resolution. Handed to a model
verbatim they dominate the context window, so every image is downscaled and
re-encoded before it leaves the server.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

# Longest edge, in pixels. A 1500px-wide screenshot is still legible for
# reading error text and inspecting layout, at a fraction of the tokens.
MAX_DIMENSION = 1500

# Ceiling on how many images a single get_issue_details call will inline.
# Anything beyond this is listed by name so the model can request it via
# get_issue_attachment.
MAX_INLINE_IMAGES = 4

IMAGE_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
)


class ImageProcessingError(Exception):
    """Attachment could not be decoded as an image."""


def is_image(attachment: dict) -> bool:
    """True if a Redmine attachment dict describes an image we can render."""
    content_type = (attachment.get("content_type") or "").split(";")[0].strip().lower()
    return content_type in IMAGE_MIME_TYPES


def downscale(raw: bytes, max_dimension: int = MAX_DIMENSION) -> bytes:
    """Downscale an image to fit within max_dimension and re-encode as PNG.

    Returns PNG bytes. Images already within bounds are still re-encoded, which
    strips EXIF and any trailing data from the original upload.
    """
    try:
        with Image.open(io.BytesIO(raw)) as img:
            # Animated GIFs / multi-frame images: take the first frame.
            img.seek(0)

            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGBA" if "A" in img.mode else "RGB")

            if max(img.size) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise ImageProcessingError(f"Could not decode attachment as an image: {e}")


def select_images(attachments: list[dict], limit: int = MAX_INLINE_IMAGES) -> tuple[list[dict], list[dict]]:
    """Split attachments into (images to inline, images left over).

    Redmine returns attachments newest-last. Screenshots added in later comments
    usually show the current state of the bug, so they are the ones worth
    inlining when we have to choose.
    """
    images = [a for a in attachments if is_image(a)]
    if len(images) <= limit:
        return images, []
    return images[-limit:], images[:-limit]
