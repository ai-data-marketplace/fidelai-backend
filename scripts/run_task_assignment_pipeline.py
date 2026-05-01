"""Manual runner for the task-assignment pipeline.

Usage:
    python scripts/run_task_assignment_pipeline.py
    python scripts/run_task_assignment_pipeline.py --mode celery

This mirrors the other pipeline runner scripts for convenience.
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
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_task_assignment_pipeline.py",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

django.setup()

from apps.processing.services.task_assignment_service import TaskAssignmentService  # noqa: E402
from apps.processing.tasks import DispatchPendingTaskAssignments  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the task-assignment pipeline manually.")
    parser.add_argument(
        "--mode",
        choices=("direct", "celery"),
        default="direct",
        help="Run the assignment service directly in-process or execute the Celery task locally.",
    )
    return parser


def run_direct():
    result = TaskAssignmentService().assign_pending_tasks()
    print("mode=direct")
    print(f"result={result}")
    return result


def run_celery():
    result = DispatchPendingTaskAssignments.apply()
    payload = result.get(propagate=True)
    print(f"mode=celery payload={payload}")
    return payload


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.mode == "celery":
            run_celery()
        else:
            run_direct()
    except Exception as exc:
        print(f"Task assignment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())