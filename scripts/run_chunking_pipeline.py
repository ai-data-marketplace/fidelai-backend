"""Manual smoke test for the chunking pipeline.

Usage:
    python scripts/run_chunking_pipeline.py <extracted_document_id>
    python scripts/run_chunking_pipeline.py <extracted_document_id> --mode celery
    python scripts/run_chunking_pipeline.py <extracted_document_id> --debug-boundaries

Notes:
- By default, chunking is idempotent: if chunks already exist, it will return the existing count.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

try:
    import django  # noqa: E402
except ModuleNotFoundError as exc:
    print(
        "Django is not installed in the Python interpreter you used. "
        "Run this script with the project venv interpreter:\n"
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_chunking_pipeline.py <extracted_document_id>",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

django.setup()

from apps.processing.models import Chunk, ExtractedDocument  # noqa: E402
from apps.processing.services.chunking import DocumentChunkingPipelineService  # noqa: E402
from apps.processing.services.chunking.types import DEFAULT_MAX_TOKENS, DEFAULT_TARGET_TOKENS  # noqa: E402
from apps.processing.tasks import ChunkExtractedDocument  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the extracted-document chunking pipeline manually.")
    parser.add_argument(
        "extracted_document_id",
        type=uuid.UUID,
        help="UUID primary key of the ExtractedDocument to chunk",
    )
    parser.add_argument(
        "--mode",
        choices=("direct", "celery"),
        default="direct",
        help="Run the chunking directly in-process or execute the Celery task locally.",
    )
    parser.add_argument(
        "--debug-boundaries",
        action="store_true",
        help="Print each planned chunk boundary and the reason it closed instead of persisting chunks.",
    )
    return parser


def run_direct(extracted_document_id: uuid.UUID):
    extracted = ExtractedDocument.objects.get(pk=extracted_document_id)
    chunks = DocumentChunkingPipelineService().chunk(extracted)
    print(f"mode=direct extracted_document_id={extracted.pk}")
    print(f"chunk_count={len(chunks)}")

    mismatches = 0
    for c in chunks[:10]:
        if c.text != extracted.full_text[c.char_start : c.char_end]:
            mismatches += 1
    print(f"sample_offset_mismatches={mismatches}")
    return len(chunks)


def run_debug_boundaries(extracted_document_id: uuid.UUID):
    extracted = ExtractedDocument.objects.get(pk=extracted_document_id)
    service = DocumentChunkingPipelineService()
    blocks = service._planner.flatten_structure(extracted.structure)
    spans = service._planner.plan_chunk_spans(
        full_text=extracted.full_text,
        blocks=blocks,
        target_tokens=DEFAULT_TARGET_TOKENS,
        max_tokens=DEFAULT_MAX_TOKENS,
    )

    print(f"mode=debug-boundaries extracted_document_id={extracted.pk}")
    print(f"planned_chunk_count={len(spans)}")
    for index, span in enumerate(spans, start=1):
        snippet = extracted.full_text[span.char_start : span.char_end].strip().replace("\n", " ")
        if len(snippet) > 140:
            snippet = snippet[:140] + "..."
        print(
            f"chunk={index} start={span.char_start} end={span.char_end} mapping_quality={span.mapping_quality:.4f} "
            f"close_reason={span.close_reason or 'unspecified'}"
        )
        print(f"  text={snippet}")

    return len(spans)


def run_celery(extracted_document_id: uuid.UUID):
    result = ChunkExtractedDocument.apply(args=(str(extracted_document_id),))
    payload = result.get(propagate=True)
    print(f"mode=celery payload={payload}")
    return payload


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.debug_boundaries:
            run_debug_boundaries(args.extracted_document_id)
        elif args.mode == "celery":
            run_celery(args.extracted_document_id)
        else:
            run_direct(args.extracted_document_id)
    except ExtractedDocument.DoesNotExist:
        print(f"ExtractedDocument {args.extracted_document_id} does not exist", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Chunking failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # Show DB truth for convenience.
    print(
        f"db_chunk_count={Chunk.objects.filter(extracted_document_id=args.extracted_document_id).count()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
