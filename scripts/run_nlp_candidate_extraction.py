"""Manual runner for NLP candidate extraction pipeline.

Usage:
    python scripts/run_nlp_candidate_extraction.py
    python scripts/run_nlp_candidate_extraction.py --mode celery
    python scripts/run_nlp_candidate_extraction.py --batch-size 100

This script processes QC-approved chunks and extracts sentiment-bearing candidate
spans using the Gemini API, creating NLPChunk records for subsequent annotation tasks.
"""

from __future__ import annotations

import argparse
import os
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
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_nlp_candidate_extraction.py",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

django.setup()

from apps.nlp.services.candidate_extraction_service import CandidateExtractionService  # noqa: E402
from apps.nlp.tasks import DispatchPendingNlpCandidateExtraction  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the NLP candidate extraction pipeline manually.")
    parser.add_argument(
        "--mode",
        choices=("direct", "celery"),
        default="direct",
        help="Run the extraction service directly in-process or execute the Celery task locally.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of chunks to process per batch (default: 50).",
    )
    return parser


def run_direct(batch_size: int):
    service = CandidateExtractionService()
    print(f"mode=direct batch_size={batch_size}")
    service.process_approved_chunks(batch_size=batch_size)
    print("NLP candidate extraction completed.")
    return {"mode": "direct", "batch_size": batch_size}


def run_celery(batch_size: int):
    result = DispatchPendingNlpCandidateExtraction.apply(args=(batch_size,))
    payload = result.get(propagate=True)
    print(f"mode=celery payload={payload}")
    return payload


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.mode == "celery":
            run_celery(args.batch_size)
        else:
            run_direct(args.batch_size)
    except Exception as exc:
        print(f"NLP candidate extraction failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
