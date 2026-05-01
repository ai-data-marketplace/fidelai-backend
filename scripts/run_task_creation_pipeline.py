"""Manual runner for the task-creation pipeline.

Usage:
    python scripts/run_task_creation_pipeline.py <extracted_document_id>
    python scripts/run_task_creation_pipeline.py <extracted_document_id> --mode celery
    python scripts/run_task_creation_pipeline.py <extracted_document_id> --max-chunks 30

This mirrors `scripts/run_chunking_pipeline.py` behaviour for convenience.
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
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_task_creation_pipeline.py <extracted_document_id>",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

django.setup()

from apps.processing.services.task_creation_service import TaskCreationService  # noqa: E402
from apps.processing.tasks import CreateAnnotationTaskFromExtractedDocument  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the task-creation pipeline for an ExtractedDocument.")
    parser.add_argument(
        "extracted_document_id",
        type=uuid.UUID,
        help="UUID primary key of the ExtractedDocument to create tasks for",
    )
    parser.add_argument(
        "--mode",
        choices=("direct", "celery"),
        default="direct",
        help="Run the task creation directly in-process or execute the Celery task locally.",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=30,
        help="Maximum number of chunks per AnnotationTask (default: 30)",
    )
    return parser


def run_direct(extracted_document_id: uuid.UUID, max_chunks: int):
    svc = TaskCreationService()
    result = svc.create_task_for_extracted_document(str(extracted_document_id), created_by=None, max_chunks_per_task=max_chunks)
    print(f"mode=direct extracted_document_id={extracted_document_id}")
    print(f"result={result}")
    return result


def run_celery(extracted_document_id: uuid.UUID, max_chunks: int):
    # call task synchronously via apply
    result = CreateAnnotationTaskFromExtractedDocument.apply(args=(str(extracted_document_id), None, max_chunks))
    payload = result.get(propagate=True)
    print(f"mode=celery payload={payload}")
    return payload


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.mode == "celery":
            run_celery(args.extracted_document_id, args.max_chunks)
        else:
            run_direct(args.extracted_document_id, args.max_chunks)
    except Exception as exc:
        print(f"Task creation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
