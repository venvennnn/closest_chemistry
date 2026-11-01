from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.config import DOCUMENTED_GEMINI_VISION_MODELS, get_settings

PROMPT = """Extract every visibly distinct garment in this outfit photograph.
Use only visible evidence. Do not invent hidden items, brands, prices, or sizes.
If an item is incomplete or occluded, say so. Bounding boxes are normalised 0-1
relative to image width/height: x, y, w, h.
Categories must be one of: top, bottom, dress, outerwear, footwear, other.
Model self-reported confidence is not a calibrated probability.
"""


class BoundingBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0, le=1)
    h: float = Field(ge=0, le=1)


class ExtractedGarment(BaseModel):
    category: str
    subtype: str | None = None
    colour: str | None = None
    colour_family: str | None = None
    pattern: str | None = None
    pattern_family: str | None = None
    formality_min: int | None = Field(default=None, ge=0, le=100)
    formality_max: int | None = Field(default=None, ge=0, le=100)
    bbox: BoundingBox
    occlusion: str = "none"
    visible_evidence: str
    model_confidence: float | None = Field(default=None, ge=0, le=1)
    incomplete: bool = False


class ExtractionPayload(BaseModel):
    garments: list[ExtractedGarment]


class GeminiError(RuntimeError):
    pass


def extract_garments(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    settings = get_settings()
    missing = settings.missing_gemini()
    if missing:
        raise GeminiError(missing)
    if settings.gemini_model not in DOCUMENTED_GEMINI_VISION_MODELS:
        raise GeminiError("GEMINI_MODEL is not a documented vision identifier.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiError("google-genai is not installed in this environment.") from exc

    client = genai.Client(api_key=settings.gemini_api_key)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ExtractionPayload,
        temperature=0.1,
    )
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                PROMPT,
            ],
            config=config,
        )
    except Exception as exc:
        raise GeminiError(
            f"Gemini request failed for model {settings.gemini_model}. "
            "Confirm the key can access this documented model. "
            f"Provider detail withheld; exception type={type(exc).__name__}."
        ) from exc

    text = getattr(response, "text", None)
    if not text:
        raise GeminiError("Gemini returned an empty body. No garments were invented.")
    try:
        payload = ExtractionPayload.model_validate_json(text)
    except ValidationError as exc:
        try:
            payload = ExtractionPayload.model_validate(json.loads(text))
        except Exception:
            raise GeminiError("Gemini JSON failed schema validation. Extraction was not stored.") from exc

    garments = []
    for item in payload.garments:
        if item.bbox.w <= 0 or item.bbox.h <= 0 or item.bbox.x + item.bbox.w > 1.01 or item.bbox.y + item.bbox.h > 1.01:
            continue
        garments.append(item.model_dump())
    return {
        "garments": garments,
        "provider": "gemini",
        "model_id": settings.gemini_model,
        "prompt_version": settings.gemini_prompt_version,
    }
