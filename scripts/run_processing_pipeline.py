"""Manual smoke test for the processing pipeline.

Usage:
    python scripts/run_processing_pipeline.py <raw_document_id>
    python scripts/run_processing_pipeline.py <raw_document_id> --mode celery
"""

from __future__ import annotations

import argparse
import os
import uuid
import sys
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
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_processing_pipeline.py <raw_document_id>",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

django.setup()

from apps.documents.models import RawDocument  # noqa: E402
from apps.processing.services.pipeline import DocumentProcessingPipelineService  # noqa: E402
from apps.processing.tasks import DocumentProcessingPipeline  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the document processing pipeline manually.")
    parser.add_argument("raw_document_id", type=uuid.UUID, help="UUID primary key of the RawDocument to process")
    parser.add_argument(
        "--mode",
        choices=("direct", "celery"),
        default="direct",
        help="Run the pipeline directly in-process or execute the Celery task locally.",
    )
    return parser


def run_direct(raw_document_id: uuid.UUID):
    raw_document = RawDocument.objects.prefetch_related("files").get(pk=raw_document_id)
    extracted_document = DocumentProcessingPipelineService().run(raw_document)
    print(f"mode=direct extracted_document_id={extracted_document.pk}")
    print(f"full_text_length={len(extracted_document.full_text or '')}")
    print(f"language_detected={extracted_document.language_detected}")
    print(f"confidence_score={extracted_document.confidence_score}")
    print(f"structure_pages={len(extracted_document.structure or [])}")
    return extracted_document.pk


def run_celery(raw_document_id: uuid.UUID):
    result = DocumentProcessingPipeline.apply(args=(raw_document_id,))
    extracted_document_id = result.get(propagate=True)
    print(f"mode=celery extracted_document_id={extracted_document_id}")
    return extracted_document_id


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.mode == "celery":
            run_celery(args.raw_document_id)
        else:
            run_direct(args.raw_document_id)
    except RawDocument.DoesNotExist:
        print(f"RawDocument {args.raw_document_id} does not exist", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())