"""
Document metadata validation service.

Architecture
------------
AbstractDocumentValidator defines the interface.  All concrete implementations
must implement `validate()`.  The active class is resolved from the Django
setting DOCUMENT_VALIDATOR_CLASS (dotted-path string), defaulting to the
GroqDocumentValidator.

To hot-swap to a local model, add to settings:
    DOCUMENT_VALIDATOR_CLASS = "apps.documents.services.validation.LocalModelValidator"

No other file in the codebase needs to change.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    reason: str
    confidence: float  # 0.0 – 1.0


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class AbstractDocumentValidator(ABC):
    """
    Interface contract for all document metadata validators.
    Implementations are fully interchangeable — the ingestion layer only
    depends on this ABC, never on a concrete class directly.
    """

    @abstractmethod
    def validate(self, text: str, domain: str, language: str) -> ValidationResult:
        """
        Verify that `text` content aligns with the contributor's claimed
        `domain` and `language`.

        Parameters
        ----------
        text:     Extracted or sampled text content (may be truncated).
        domain:   Contributor-declared domain (e.g. "health", "law").
        language: Contributor-declared language (e.g. "amharic").

        Returns a ValidationResult — never raises.
        """


# ---------------------------------------------------------------------------
# Groq (llama3-70b-8192) concrete implementation
# ---------------------------------------------------------------------------

_GROQ_MODEL = "llama3-70b-8192"
_MAX_TEXT_CHARS = 2_000  # stay well within token limits for a preview call

_SYSTEM_PROMPT = (
    "You are a content auditor for an Amharic AI data marketplace. "
    "Your task is to verify that a text excerpt matches the contributor's "
    "claimed domain and language. Respond in JSON only, with exactly three keys: "
    '{"is_valid": true|false, "confidence": 0.0-1.0, "reason": "one sentence"}. '
    "is_valid must be true only when the text is plausibly aligned with the domain "
    "and is predominantly the declared language. Do not explain further."
)


class GroqDocumentValidator(AbstractDocumentValidator):
    """
    Uses the Groq Cloud API (llama3-70b-8192) to validate domain/language
    alignment.  GROQ_API_KEY is read exclusively from the environment — it
    must never appear in the codebase.
    """

    def __init__(self):
        try:
            from groq import Groq  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "The 'groq' package is required. Run: pip install groq"
            ) from exc

        api_key = os.environ.get("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", None)
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        self._client = Groq(api_key=api_key)

    def validate(self, text: str, domain: str, language: str) -> ValidationResult:
        preview = (text or "").strip()[:_MAX_TEXT_CHARS]
        if not preview:
            return ValidationResult(
                is_valid=False,
                reason="No text content was available for validation.",
                confidence=1.0,
            )

        user_message = (
            f"Domain: {domain}\n"
            f"Language: {language}\n\n"
            f"Text excerpt:\n{preview}"
        )

        try:
            response = self._client.chat.completions.create(
                model=_GROQ_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,
                max_tokens=128,
            )
            raw = response.choices[0].message.content or ""
            return self._parse_response(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GroqDocumentValidator error: %s", exc, exc_info=True)
            # Fail open: if the validator is unavailable, don't block the submission.
            return ValidationResult(
                is_valid=True,
                reason=f"Validation service unavailable ({type(exc).__name__}); defaulting to approved.",
                confidence=0.0,
            )

    @staticmethod
    def _parse_response(raw: str) -> ValidationResult:
        import json
        import re

        # Extract JSON even if the model wraps it in markdown fences.
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if not match:
            return ValidationResult(
                is_valid=True,
                reason="Could not parse validator response; defaulting to approved.",
                confidence=0.0,
            )
        try:
            data = json.loads(match.group())
            return ValidationResult(
                is_valid=bool(data.get("is_valid", True)),
                reason=str(data.get("reason", "")),
                confidence=float(data.get("confidence", 0.0)),
            )
        except (json.JSONDecodeError, ValueError):
            return ValidationResult(
                is_valid=True,
                reason="Malformed validator response; defaulting to approved.",
                confidence=0.0,
            )


# ---------------------------------------------------------------------------
# Local model stub — future hot-swap target
# ---------------------------------------------------------------------------


class LocalModelValidator(AbstractDocumentValidator):
    """
    Placeholder for a locally hosted fine-tuned Amharic model.
    Swap in via: DOCUMENT_VALIDATOR_CLASS = "...LocalModelValidator"
    """

    def validate(self, text: str, domain: str, language: str) -> ValidationResult:
        raise NotImplementedError(
            "LocalModelValidator is not yet implemented. "
            "Configure a real local model endpoint here."
        )


# ---------------------------------------------------------------------------
# Resolver — used by tasks and services; never imports a concrete class directly
# ---------------------------------------------------------------------------

_DEFAULT_VALIDATOR_CLASS = "apps.documents.services.validation.GroqDocumentValidator"


def get_validator() -> AbstractDocumentValidator:
    """
    Return the configured validator instance.
    Reads DOCUMENT_VALIDATOR_CLASS from Django settings (dotted import path).
    """
    dotted_path = getattr(settings, "DOCUMENT_VALIDATOR_CLASS", _DEFAULT_VALIDATOR_CLASS)
    cls = import_string(dotted_path)
    return cls()
