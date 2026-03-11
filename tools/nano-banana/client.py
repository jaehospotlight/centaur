"""Nano Banana (Gemini image generation) client."""

from __future__ import annotations

import base64
import json
import mimetypes
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from shared.tool_sdk import secret


MODELS: dict[str, dict[str, str]] = {
    "flash": {
        "id": "gemini-3.1-flash-image-preview",
        "label": "Nano Banana 2",
        "description": "Fast image generation/editing with thinking and search grounding.",
    },
    "pro": {
        "id": "gemini-3-pro-image-preview",
        "label": "Nano Banana Pro",
        "description": "Higher-quality image generation/editing for polished assets.",
    },
}

DEFAULT_MODEL = "flash"
_DEFAULT_OUTPUT_MIME_TYPE = "image/png"
_MIME_TYPE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class NanoBananaClient:
    """Client for Google's Nano Banana image generation models."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key
        self._client: genai.Client | None = None

    def _get_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        key = secret("GOOGLE_API_KEY", "")
        if key:
            return key
        raise RuntimeError("GOOGLE_API_KEY not set.")

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self._get_api_key())
        return self._client

    def _resolve_model(self, model: str) -> tuple[str, dict[str, str]]:
        key = (model or DEFAULT_MODEL).strip().lower()
        if key in MODELS:
            return key, MODELS[key]
        return model, {"id": model, "label": model, "description": ""}

    def _build_generate_config(
        self,
        *,
        aspect_ratio: str | None,
        image_size: str | None,
        person_generation: str | None,
        output_mime_type: str | None,
        output_compression_quality: int | None,
        use_google_search: bool,
        thinking_budget: int | None,
        thinking_level: str | None,
    ) -> types.GenerateContentConfig:
        config_kwargs: dict[str, Any] = {
            "response_modalities": ["TEXT", "IMAGE"],
        }

        image_config_kwargs: dict[str, Any] = {}
        if aspect_ratio:
            image_config_kwargs["aspect_ratio"] = aspect_ratio
        if image_size:
            image_config_kwargs["image_size"] = image_size
        if person_generation:
            image_config_kwargs["person_generation"] = person_generation.upper()
        if output_mime_type:
            image_config_kwargs["output_mime_type"] = output_mime_type
        if output_compression_quality is not None:
            image_config_kwargs["output_compression_quality"] = output_compression_quality
        if image_config_kwargs:
            config_kwargs["image_config"] = types.ImageConfig(**image_config_kwargs)

        thinking_kwargs: dict[str, Any] = {}
        if thinking_budget is not None:
            thinking_kwargs["thinking_budget"] = thinking_budget
        if thinking_level:
            thinking_kwargs["thinking_level"] = thinking_level.upper()
        if thinking_kwargs:
            config_kwargs["thinking_config"] = types.ThinkingConfig(**thinking_kwargs)

        if use_google_search:
            config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

        return types.GenerateContentConfig(**config_kwargs)

    def _infer_image_mime_type(self, path: Path) -> str:
        guessed, _ = mimetypes.guess_type(path.name)
        return guessed or _DEFAULT_OUTPUT_MIME_TYPE

    def _build_image_part(
        self,
        *,
        image_path: str | None,
        image_base64: str | None,
        image_mime_type: str | None,
    ) -> types.Part:
        if image_path and image_base64:
            raise ValueError("Provide either image_path or image_base64, not both.")
        if not image_path and not image_base64:
            raise ValueError("Either image_path or image_base64 is required.")

        if image_path:
            path = Path(image_path)
            if not path.exists():
                raise FileNotFoundError(f"Image not found: {path}")
            image_bytes = path.read_bytes()
            mime_type = image_mime_type or self._infer_image_mime_type(path)
        else:
            try:
                image_bytes = base64.b64decode(image_base64 or "", validate=True)
            except Exception as exc:  # pragma: no cover - exact decoder error text is irrelevant
                raise ValueError("image_base64 is not valid base64.") from exc
            mime_type = image_mime_type or _DEFAULT_OUTPUT_MIME_TYPE

        return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    def _extract_response_text(self, response: Any) -> str | None:
        parts = getattr(response, "parts", None) or []
        text_parts = [part.text.strip() for part in parts if getattr(part, "text", None)]
        return "\n".join(text_parts) if text_parts else None

    def _extract_generated_image(self, response: Any) -> tuple[bytes, str]:
        parts = getattr(response, "parts", None) or []
        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            if inline_data is not None and getattr(inline_data, "data", None):
                mime_type = getattr(inline_data, "mime_type", None) or _DEFAULT_OUTPUT_MIME_TYPE
                return inline_data.data, mime_type

        text_response = self._extract_response_text(response)
        if text_response:
            raise RuntimeError(f"No image was generated. Model response: {text_response}")
        raise RuntimeError("No image was generated.")

    def _default_filename(self, mime_type: str, prefix: str) -> str:
        suffix = _MIME_TYPE_EXTENSIONS.get(
            mime_type,
            mimetypes.guess_extension(mime_type, strict=False) or ".png",
        )
        return f"{prefix}-{int(time.time())}{suffix}"

    def _format_result(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        model_key: str,
        model_info: dict[str, str],
        filename: str | None,
        text_response: str | None,
    ) -> str:
        payload: dict[str, Any] = {
            "status": "ok",
            "model": model_key,
            "model_id": model_info["id"],
            "mime_type": mime_type,
            "filename": filename or self._default_filename(mime_type, "nano-banana"),
            "size_bytes": len(image_bytes),
            "content_base64": base64.b64encode(image_bytes).decode("ascii"),
        }
        if text_response:
            payload["text_response"] = text_response
        return json.dumps(payload, separators=(",", ":"))

    def list_models(self) -> list[dict[str, str]]:
        """List available Nano Banana models."""
        return [
            {
                "name": name,
                "id": info["id"],
                "label": info["label"],
                "description": info["description"],
            }
            for name, info in MODELS.items()
        ]

    def generate(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        aspect_ratio: str | None = None,
        image_size: str | None = None,
        person_generation: str | None = None,
        output_mime_type: str | None = None,
        output_compression_quality: int | None = None,
        use_google_search: bool = False,
        thinking_budget: int | None = None,
        thinking_level: str | None = None,
        filename: str | None = None,
    ) -> str:
        """Generate an image and return a JSON payload with base64 image bytes."""
        model_key, model_info = self._resolve_model(model)
        response = self.client.models.generate_content(
            model=model_info["id"],
            contents=[prompt],
            config=self._build_generate_config(
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                person_generation=person_generation,
                output_mime_type=output_mime_type,
                output_compression_quality=output_compression_quality,
                use_google_search=use_google_search,
                thinking_budget=thinking_budget,
                thinking_level=thinking_level,
            ),
        )

        image_bytes, mime_type = self._extract_generated_image(response)
        return self._format_result(
            image_bytes=image_bytes,
            mime_type=mime_type,
            model_key=model_key,
            model_info=model_info,
            filename=filename,
            text_response=self._extract_response_text(response),
        )

    def edit(
        self,
        prompt: str,
        image_path: str | None = None,
        image_base64: str | None = None,
        image_mime_type: str | None = None,
        model: str = DEFAULT_MODEL,
        aspect_ratio: str | None = None,
        image_size: str | None = None,
        person_generation: str | None = None,
        output_mime_type: str | None = None,
        output_compression_quality: int | None = None,
        use_google_search: bool = False,
        thinking_budget: int | None = None,
        thinking_level: str | None = None,
        filename: str | None = None,
    ) -> str:
        """Edit an image and return a JSON payload with base64 image bytes."""
        model_key, model_info = self._resolve_model(model)
        image_part = self._build_image_part(
            image_path=image_path,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
        )
        response = self.client.models.generate_content(
            model=model_info["id"],
            contents=[image_part, prompt],
            config=self._build_generate_config(
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                person_generation=person_generation,
                output_mime_type=output_mime_type,
                output_compression_quality=output_compression_quality,
                use_google_search=use_google_search,
                thinking_budget=thinking_budget,
                thinking_level=thinking_level,
            ),
        )

        image_bytes, mime_type = self._extract_generated_image(response)
        return self._format_result(
            image_bytes=image_bytes,
            mime_type=mime_type,
            model_key=model_key,
            model_info=model_info,
            filename=filename,
            text_response=self._extract_response_text(response),
        )


def _client() -> NanoBananaClient:
    return NanoBananaClient()
