"""Manual runner for the expert task creation pipeline.

Usage:
    python scripts/run_expert_task_creation_pipeline.py
    python scripts/run_expert_task_creation_pipeline.py --mode celery
    python scripts/run_expert_task_creation_pipeline.py --batch-size 100 --max-chunks-per-task 10
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
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_expert_task_creation_pipeline.py",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

django.setup()

from apps.processing.services.expert_task_creation_service import ExpertTaskCreationService  # noqa: E402
from apps.processing.tasks import DispatchPendingExpertTasks  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the expert task creation pipeline manually.")
    parser.add_argument(
        "--mode",
        choices=("direct", "celery"),
        default="direct",
        help="Run expert task creation directly in-process or execute the Celery task locally.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Maximum number of escalated chunks to inspect in one run.",
    )
    parser.add_argument(
        "--max-chunks-per-task",
        type=int,
        default=10,
        help="Maximum number of chunks to place in a single expert task.",
    )
    return parser


def run_direct(batch_size: int, max_chunks_per_task: int):
    result = ExpertTaskCreationService().create_expert_tasks_from_escalated_chunks(
        max_chunks_per_task=max_chunks_per_task,
        chunk_limit=batch_size,
    )
    print("mode=direct")
    print(f"result={result}")
    return result


def run_celery(batch_size: int, max_chunks_per_task: int):
    result = DispatchPendingExpertTasks.apply(args=(batch_size, max_chunks_per_task))
    payload = result.get(propagate=True)
    print(f"mode=celery payload={payload}")
    return payload


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.mode == "celery":
            run_celery(args.batch_size, args.max_chunks_per_task)
        else:
            run_direct(args.batch_size, args.max_chunks_per_task)
    except Exception as exc:
        print(f"Expert task creation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())