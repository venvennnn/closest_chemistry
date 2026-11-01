from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageOps

from app.config import get_settings

SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"RIFF", "image/webp"),
)


class ImageValidationError(ValueError):
    pass


def sniff_mime(data: bytes) -> str:
    for prefix, mime in SIGNATURES:
        if data.startswith(prefix):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    raise ImageValidationError("Unsupported image signature. Upload JPEG, PNG, or WebP.")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalise_image(data: bytes) -> tuple[bytes, dict]:
    settings = get_settings()
    if len(data) > settings.max_upload_bytes:
        raise ImageValidationError(f"File exceeds {settings.max_upload_bytes} bytes.")
    mime = sniff_mime(data)
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise ImageValidationError("Image could not be decoded.") from exc

    image = ImageOps.exif_transpose(image)
    if image.width < settings.min_image_side or image.height < settings.min_image_side:
        raise ImageValidationError(
            f"Each side must be at least {settings.min_image_side}px after orientation correction."
        )
    if max(image.width, image.height) > settings.max_image_side:
        raise ImageValidationError(f"Longest side must be at most {settings.max_image_side}px.")

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    # Strip EXIF by rewriting pixels only.
    buffer = io.BytesIO()
    save_mime = "JPEG" if mime == "image/jpeg" else "PNG" if mime == "image/png" else "WEBP"
    if save_mime == "JPEG" and image.mode == "RGBA":
        image = image.convert("RGB")
    image.save(buffer, format=save_mime, quality=92)
    payload = buffer.getvalue()
    return payload, {
        "mime_type": "image/jpeg" if save_mime == "JPEG" else "image/png" if save_mime == "PNG" else "image/webp",
        "width": image.width,
        "height": image.height,
        "byte_size": len(payload),
        "content_sha256": sha256_hex(payload),
        "exif_stripped": True,
        "orientation_normalised": True,
    }


def crop_box(data: bytes, bbox: dict, mime_type: str = "image/jpeg") -> bytes:
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    left = max(0.0, min(1.0, float(bbox.get("x", 0))))
    top = max(0.0, min(1.0, float(bbox.get("y", 0))))
    width = max(0.0, min(1.0 - left, float(bbox.get("w", 0))))
    height = max(0.0, min(1.0 - top, float(bbox.get("h", 0))))
    if width <= 0 or height <= 0:
        raise ImageValidationError("Bounding box is outside the image.")
    box = (
        int(left * image.width),
        int(top * image.height),
        int((left + width) * image.width),
        int((top + height) * image.height),
    )
    cropped = image.crop(box)
    if cropped.mode != "RGB":
        cropped = cropped.convert("RGB")
    buffer = io.BytesIO()
    cropped.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()
