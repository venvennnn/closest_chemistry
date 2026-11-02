import io

import pytest
from PIL import Image

from app.services.images import ImageValidationError, normalise_image
from app.services.ssrf import FetchError, validate_public_https


def _png(size=(200, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(20, 40, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_normalise_strips_and_accepts_real_png():
    payload, meta = normalise_image(_png())
    assert meta["exif_stripped"] is True
    assert meta["width"] == 200
    assert meta["content_sha256"]
    assert payload.startswith(b"\x89PNG") or payload[:3] == b"\xff\xd8"


def test_downscales_oversized_photos():
    payload, meta = normalise_image(_png((5000, 1200)))
    assert meta["width"] <= 4096
    assert meta["height"] <= 4096
    assert max(meta["width"], meta["height"]) == 4096
    assert payload


def test_rejects_tiny_and_garbage():
    with pytest.raises(ImageValidationError):
        normalise_image(b"not-an-image")
    with pytest.raises(ImageValidationError):
        normalise_image(_png((20, 20)))


def test_blocks_private_urls():
    with pytest.raises(FetchError):
        validate_public_https("http://example.com")
    with pytest.raises(FetchError):
        validate_public_https("https://127.0.0.1/product")
    with pytest.raises(FetchError):
        validate_public_https("https://localhost/product")
