"""Manual runner for NLP consensus pipeline.

Usage:
    python scripts/run_nlp_consensus.py
    python scripts/run_nlp_consensus.py --mode celery
    python scripts/run_nlp_consensus.py --batch-size 100
    python scripts/run_nlp_consensus.py --force

This script runs consensus on completed NLP annotation tasks to derive final labels.
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
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_nlp_consensus.py",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

django.setup()

from apps.nlp.services.nlp_consensus_service import NLPConsensusService  # noqa: E402
from apps.nlp.tasks import DispatchNlpConsensus  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the NLP consensus pipeline manually.")
    parser.add_argument(
        "--mode",
        choices=("direct", "celery"),
        default="direct",
        help="Run the consensus service directly in-process or execute the Celery task locally.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of assignments to process per batch (default: 100).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force consensus computation even for tasks that may have recent edits.",
    )
    return parser


def run_direct(batch_size: int, force: bool):
    service = NLPConsensusService()
    print(f"mode=direct batch_size={batch_size} force={force}")
    summary = service.compute_consensus(batch_size=batch_size, force=force)
    print(f"result={summary}")
    return summary


def run_celery(batch_size: int, force: bool):
    result = DispatchNlpConsensus.apply(args=(batch_size, force))
    payload = result.get(propagate=True)
    print(f"mode=celery payload={payload}")
    return payload


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.mode == "celery":
            run_celery(args.batch_size, args.force)
        else:
            run_direct(args.batch_size, args.force)
    except Exception as exc:
        print(f"NLP consensus failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
