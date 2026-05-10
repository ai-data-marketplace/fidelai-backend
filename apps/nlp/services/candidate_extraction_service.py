"""
Candidate extraction service for the `nlp` app.

Responsibilities:
- Read QC-approved `processing.Chunk` rows (status == APPROVED)
- Send chunk text to Gemini (via `google.generativeai` if available)
- Parse JSON-only responses containing candidate sentiment-bearing spans
- Validate and deduplicate candidates
- Create `nlp.NLPChunk` records with AI metadata

This service is intentionally modular and extensible for other NLP tasks.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction
from django.utils import timezone

from apps.common.models.base import TimeStampedModel
from apps.processing.models.chunk import Chunk, ChunkStatusChoices
from apps.nlp.models.nlp_chunk import NLPChunk
from apps.nlp.models.choices import NLPTaskTypeChoices

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("NLP_CANDIDATE_CONFIDENCE_THRESHOLD", 0.6))
DEFAULT_BATCH_SIZE = int(os.getenv("NLP_CANDIDATE_BATCH_SIZE", 50))


class GeminiClientError(RuntimeError):
    pass


@dataclass
class Candidate:
    text: str
    candidate_sentiment: str
    confidence: float


class CandidateExtractionService:
    """Service that extracts NLP candidate chunks from QC-approved chunks.

    Usage:
        svc = CandidateExtractionService()
        svc.process_approved_chunks(batch_size=50)
    """

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        self.model_name = model_name or os.getenv("GEMINI_MODEL_NAME")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        # lazy import of gemini client
        self._gemini = None

    # ---------------------- Public batch entrypoint ----------------------
    def process_approved_chunks(self, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        """Process QC-approved chunks in a memory-efficient, batched manner.

        Iterates over `processing.Chunk` objects with `status == APPROVED` and
        processes them one-by-one. Errors are handled per-chunk so the batch
        does not crash on API errors or malformed responses.
        """
        qs = Chunk.objects.filter(status=ChunkStatusChoices.APPROVED).order_by("created_at")

        processed = 0
        created = 0
        skipped = 0

        buffer = []
        for chunk in qs.iterator():
            buffer.append(chunk)
            if len(buffer) >= batch_size:
                p, c, s = self._process_chunk_batch(buffer)
                processed += p
                created += c
                skipped += s
                buffer = []
        # final partial batch
        if buffer:
            p, c, s = self._process_chunk_batch(buffer)
            processed += p
            created += c
            skipped += s

        logger.info("Candidate extraction completed: processed=%d created=%d skipped=%d", processed, created, skipped)

    # ---------------------- Batch helper ----------------------
    def _process_chunk_batch(self, chunks: Iterable[Chunk]) -> (int, int, int):
        processed = 0
        created = 0
        skipped = 0
        for chunk in chunks:
            try:
                p, c, s = self.process_chunk(chunk)
                processed += p
                created += c
                skipped += s
            except Exception as e:
                # Log and continue
                logger.exception("Failed processing chunk id=%s: %s", getattr(chunk, "id", None), str(e))
        return processed, created, skipped

    # ---------------------- Per-chunk processing ----------------------
    def process_chunk(self, chunk: Chunk) -> (int, int, int):
        """Process a single approved `Chunk` and create NLPChunk records.

        Returns tuple: (processed_candidates, created_chunks, skipped_candidates)
        """
        logger.debug("Processing chunk id=%s", chunk.id)

        prompt = self.build_prompt(chunk.text, getattr(chunk, "metadata", {}) or {}, source_domain=chunk.extracted_document and getattr(chunk.extracted_document, "language_detected", ""))

        try:
            raw = self.call_gemini(prompt)
        except Exception as e:
            # Log the error and skip this chunk
            logger.exception("Gemini call failed for chunk id=%s: %s", chunk.id, str(e))
            return 0, 0, 0

        candidates = self.parse_response(raw)
        processed = 0
        created = 0
        skipped = 0

        if not candidates:
            logger.info("No candidates returned for chunk id=%s", chunk.id)
            return 0, 0, 0

        # fetch existing NLPChunks for dedup check limited to this source chunk & task
        existing_qs = NLPChunk.objects.filter(source_chunk=chunk, task_type=NLPTaskTypeChoices.SENTIMENT)
        existing_texts = [self.normalize_text(e.text) for e in existing_qs]

        for cand in candidates:
            processed += 1
            if not self.validate_candidate(cand):
                skipped += 1
                logger.debug("Candidate validation failed for chunk=%s candidate=%r", chunk.id, cand)
                continue

            normalized = self.normalize_text(cand.text)
            if normalized in existing_texts:
                skipped += 1
                logger.debug("Duplicate candidate skipped for chunk=%s text=%s", chunk.id, cand.text)
                continue

            # create NLPChunk record
            try:
                n = self.create_nlp_chunk(
                    source_chunk=chunk,
                    task_type=NLPTaskTypeChoices.SENTIMENT,
                    text=cand.text,
                    source_context=chunk.text,
                    source_domain=chunk.extracted_document and getattr(chunk.extracted_document, "language_detected", "") or "",
                    generated_by_ai=True,
                    ai_model_name=self.model_name or "",
                    ai_confidence_score=cand.confidence,
                    metadata={
                        "candidate_sentiment": cand.candidate_sentiment,
                        "extraction_method": "gemini",
                        "extraction_timestamp": timezone.now().isoformat(),
                        "gemini_model": self.model_name,
                        "source_chunk_id": str(chunk.id),
                    },
                )
                existing_texts.append(normalized)
                created += 1
                logger.info("Created NLPChunk id=%s from chunk=%s", n.id, chunk.id)
            except Exception:
                skipped += 1
                logger.exception("Failed to create NLPChunk for chunk=%s candidate=%r", chunk.id, cand)

        return processed, created, skipped

    # ---------------------- Prompting and Gemini call ----------------------
    def build_prompt(self, chunk_text: str, chunk_metadata: Dict[str, Any], source_domain: str = "") -> str:
        """Build a structured prompt to send to Gemini.

        The prompt instructs Gemini to output JSON-only: a list of candidate objects
        containing `text`, `candidate_sentiment`, and `confidence`.
        """
        # Keep prompt clear and structured for stable JSON response
        instruction = (
            "You will receive a paragraph of text from a QC-approved document chunk. "
            "Identify ONLY sentiment-bearing spans written in Amharic (Ethiopic script). "
            "Do NOT extract English, Arabic, Chinese, or any other non-Amharic text. "
            "Do NOT include purely factual sentences, headings, metadata, or irrelevant fragments. "
            "For each candidate, return a JSON object with fields: \n"
            "- text: the exact candidate text (string)\n"
            "- candidate_sentiment: one of 'positive', 'negative', 'neutral'\n"
            "- confidence: float between 0 and 1 indicating model confidence\n"
            "Return ONLY a JSON array of such objects. The `text` field must contain Amharic text exactly as it appears in the chunk. "
            "Do NOT include any explanation, markdown, or additional text."
        )

        # Provide domain and a small instruction to prefer compact candidate spans
        domain_hint = f"Source domain: {source_domain}." if source_domain else ""

        prompt = f"{instruction}\n{domain_hint}\nCHUNK_TEXT:\n{chunk_text}\n\nJSON:" 
        return prompt

    def call_gemini(self, prompt: str) -> Any:
        """Call Gemini API (via `google.generativeai` package) and return the raw response.

        Raises GeminiClientError on failure. This method isolates the external dependency.
        """
        try:
            import google.generativeai as genai
        except Exception as e:
            raise GeminiClientError("google.generativeai package not available; please install it") from e

        if not self.api_key:
            raise GeminiClientError("GEMINI_API_KEY not provided")
        if not self.model_name:
            raise GeminiClientError("GEMINI_MODEL_NAME not provided")

        try:
            # Configure the API key
            genai.configure(api_key=self.api_key)
            
            # Use the GenerativeModel API (current version)
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt)
            return response
        except Exception as e:
            raise GeminiClientError(f"Gemini API call failed: {e}") from e

    # ---------------------- Response parsing ----------------------
    def parse_response(self, response: Any) -> List[Candidate]:
        """Parse the Gemini response into a list of Candidate objects.

        This method is defensive and handles various SDK response shapes.
        """
        raw_text = None

        # SDK specific response handling
        try:
            # New SDK (0.8+) returns response with .text attribute
            if hasattr(response, "text") and isinstance(response.text, str):
                raw_text = response.text
            # Sometimes it's in parts
            elif hasattr(response, "parts") and response.parts:
                text_parts = []
                for part in response.parts:
                    if hasattr(part, "text"):
                        text_parts.append(part.text)
                if text_parts:
                    raw_text = " ".join(text_parts)
            # Fallback: convert to string
            if not raw_text:
                raw_text = str(response)
        except Exception:
            raw_text = str(response)

        # Extract JSON substring if the model returned extra content
        json_blob = self._extract_json_from_text(raw_text)
        if not json_blob:
            logger.warning("Could not locate JSON in Gemini response: %s", raw_text[:200] if raw_text else "None")
            return []

        try:
            parsed = json.loads(json_blob)
        except Exception:
            logger.exception("Failed to parse JSON from Gemini output")
            return []

        candidates: List[Candidate] = []
        if not isinstance(parsed, list):
            logger.warning("Gemini response JSON is not a list")
            return []

        for item in parsed:
            try:
                text = item.get("text") if isinstance(item, dict) else None
                sentiment = item.get("candidate_sentiment") if isinstance(item, dict) else None
                confidence = item.get("confidence") if isinstance(item, dict) else None

                if text is None or sentiment is None or confidence is None:
                    # skip malformed entries
                    logger.debug("Skipping malformed candidate entry: %r", item)
                    continue

                # force numeric confidence
                confidence = float(confidence)
                candidates.append(Candidate(text=text.strip(), candidate_sentiment=str(sentiment), confidence=confidence))
            except Exception:
                logger.exception("Failed to parse candidate item: %r", item)
                continue

        return candidates

    def _extract_json_from_text(self, text: Optional[str]) -> Optional[str]:
        """Attempt to extract a JSON array substring from text.

        Returns the JSON string or None.
        """
        if not text:
            return None

        # find first '[' and last ']' to capture JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start : end + 1]

    # ---------------------- Validation & normalization ----------------------
    def validate_candidate(self, candidate: Candidate, min_confidence: float = DEFAULT_CONFIDENCE_THRESHOLD) -> bool:
        """Run a series of heuristic checks to determine whether the candidate is acceptable.

        Reject if empty, too short, low confidence, non-Amharic, or obvious garbage.
        """
        text = candidate.text
        if not text:
            return False

        # normalize unicode
        try:
            text = unicodedata.normalize("NFC", text)
        except Exception:
            pass

        if len(text.strip()) < 5:
            return False

        # Require Amharic/Ethiopic script only so we only extract the current target language.
        if not self._is_amharic_only(text):
            return False

        # confidence threshold
        if candidate.confidence is None:
            return False
        if candidate.confidence < min_confidence:
            return False

        # repeated punctuation (e.g., "!!!!!!")
        if re.search(r"([!\"'()\[\]{}\\/\\|<>?~`@#$%^&*_+=;:-])\1{3,}", text):
            return False

        # obvious garbage (control chars)
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
            return False

        # malformed unicode sequences
        try:
            text.encode("utf-8")
        except Exception:
            return False

        # short-word-only strings (e.g., "ok ok ok")
        if len(re.findall(r"\w+", text)) < 2:
            return False

        return True

    def _is_amharic_only(self, text: str) -> bool:
        """Return True when the text is written in Ethiopic/Amharic script only.

        Punctuation, whitespace, and digits are allowed, but any alphabetic character
        outside the Ethiopic ranges causes rejection.
        """
        if not text:
            return False

        has_amharic = False
        for char in text:
            if char.isalpha():
                if not re.match(r"[\u1200-\u137F\u1380-\u139F]", char):
                    return False
                has_amharic = True

        return has_amharic

    def normalize_text(self, text: str) -> str:
        """Normalize text for deduplication comparisons.

        Steps:
        - Unicode normalize
        - Trim
        - Collapse whitespace
        - Remove repeated punctuation
        - Lowercase for stability
        """
        if text is None:
            return ""
        try:
            t = unicodedata.normalize("NFC", text)
        except Exception:
            t = text
        t = t.strip()
        # collapse whitespace
        t = re.sub(r"\s+", " ", t)
        # collapse repeated punctuation to single
        t = re.sub(r"([!?.])\1+", r"\1", t)
        # lowercase for deduping
        t = t.lower()
        return t

    # ---------------------- Creation ----------------------
    @transaction.atomic
    def create_nlp_chunk(
        self,
        source_chunk: Chunk,
        task_type: str,
        text: str,
        source_context: str,
        source_domain: str,
        generated_by_ai: bool,
        ai_model_name: Optional[str],
        ai_confidence_score: Optional[float],
        metadata: Dict[str, Any],
    ) -> NLPChunk:
        """Persist an NLPChunk record. Transactional per creation.

        Caller must ensure deduplication before calling this method.
        """
        n = NLPChunk.objects.create(
            source_chunk=source_chunk,
            task_type=task_type,
            text=text,
            order_index=0,  # order_index can be set later when creating tasks
            char_start=0,
            char_end=len(text),
            metadata=metadata,
            generated_by_ai=generated_by_ai,
            ai_model_name=ai_model_name,
            ai_confidence_score=ai_confidence_score,
            source_context=source_context,
            source_domain=source_domain,
            status="ready_for_annotation",
            is_active=True,
            requires_human_review=False,
        )
        return n

    # ---------------------- Utility / testing helpers ----------------------
    def _fake_gemini_response_for_tests(self, chunk_text: str) -> str:
        """Return a deterministic fake JSON response used for unit testing.

        Not used in production.
        """
        example = [
            {"text": chunk_text.split(".")[0], "candidate_sentiment": "positive", "confidence": 0.85}
        ]
        return json.dumps(example)


# End of file
