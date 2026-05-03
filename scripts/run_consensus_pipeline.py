"""Manual runner for the consensus pipeline.

Usage:
    python scripts/run_consensus_pipeline.py
    python scripts/run_consensus_pipeline.py --mode celery
    python scripts/run_consensus_pipeline.py --batch-size 200
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
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_consensus_pipeline.py",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

django.setup()

from apps.processing.services.consensus_service import ConsensusPipelineService  # noqa: E402
from apps.processing.tasks import DispatchPendingConsensus  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the consensus pipeline manually.")
    parser.add_argument(
        "--mode",
        choices=("direct", "celery"),
        default="direct",
        help="Run consensus directly in-process or execute the Celery task locally.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Maximum number of chunks to stream per DB iterator batch.",
    )
    return parser


def run_direct(batch_size: int):
    result = ConsensusPipelineService().run_pipeline(batch_size=batch_size)
    print("mode=direct")
    print(f"result={result}")
    return result


def run_celery(batch_size: int):
    result = DispatchPendingConsensus.apply(args=(batch_size,))
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
        print(f"Consensus pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
