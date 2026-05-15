"""Manual runner for NLP task assignment pipeline.

Usage:
    python scripts/run_nlp_task_assignment.py
    python scripts/run_nlp_task_assignment.py --mode celery

This script assigns NLP annotation tasks to available annotators.
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
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_nlp_task_assignment.py",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

django.setup()

from apps.nlp.services.nlp_task_assignment_service import NLPTaskAssignmentService  # noqa: E402
from apps.nlp.tasks import DispatchNlpTaskAssignment  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the NLP task assignment pipeline manually.")
    parser.add_argument(
        "--mode",
        choices=("direct", "celery"),
        default="direct",
        help="Run the assignment service directly in-process or execute the Celery task locally.",
    )
    return parser


def run_direct():
    service = NLPTaskAssignmentService()
    print("mode=direct")
    summary = service.assign_tasks()
    print(f"result={summary}")
    return summary


def run_celery():
    result = DispatchNlpTaskAssignment.apply()
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
        print(f"NLP task assignment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
