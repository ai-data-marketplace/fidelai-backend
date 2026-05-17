"""Manual runner for Dataset Aggregation task.

Usage:
    python scripts/run_dataset_aggregation.py --task-type sentiment --min-agreement-score 0.8 --max-examples 1000 --balance-labels --created-by-id 1 --license-type mit --price 1000 --mode direct
    python scripts/run_dataset_aggregation.py --mode celery

This script runs the `DispatchDatasetAggregation` task directly or via Celery.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from django.contrib.auth import get_user_model


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
        "  c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_dataset_aggregation.py",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


django.setup()

from apps.datasets.services.aggregation_service import DatasetAggregationService  # noqa: E402
from apps.datasets.tasks import DispatchDatasetAggregation  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run dataset aggregation task manually.")
    parser.add_argument("--mode", choices=("direct", "celery"), default="direct")
    parser.add_argument("--task-type", default=None, help="Optional NLP task type override e.g. sentiment, ner")
    parser.add_argument("--domains", default=None, help="Comma-separated list of domains or single domain string")
    parser.add_argument("--min-agreement-score", type=float, default=0.8)
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--balance-labels", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=None)
    parser.add_argument("--license-type", default="mit")
    parser.add_argument("--price", type=float, default=1000.0)
    return parser


def _parse_domains(domains: str | None) -> list[str]:
    if domains is None:
        return []
    return [d.strip() for d in domains.split(",") if d.strip()]


def run_direct(args):
    service = DatasetAggregationService()
    domains = _parse_domains(args.domains)
    created_by = None
    if args.created_by_id is not None:
        created_by = get_user_model().objects.filter(pk=args.created_by_id).first()
    print(f"mode=direct task_type={args.task_type} domains={domains} min_agreement_score={args.min_agreement_score} max_examples={args.max_examples} balance_labels={args.balance_labels} created_by_id={args.created_by_id} license_type={args.license_type} price={args.price}")
    dataset = service.build_dataset(
        task_type=args.task_type,
        domains=domains,
        min_agreement_score=args.min_agreement_score,
        max_examples=args.max_examples,
        balance_labels=args.balance_labels,
        created_by=created_by,
        license_type=args.license_type,
        price=args.price,
    )

    result = {
        "queued": False,
        "dataset_id": str(dataset.pk),
        "title": dataset.title,
        "task_type": dataset.nlp_task_type,
        "asset_count": dataset.assets.count(),
        "chunk_count": dataset.dataset_chunks.count(),
    }
    print(f"result={result}")
    return result


def run_celery(args):
    # DispatchCelery task expects same signature
    domains = _parse_domains(args.domains)
    result = DispatchDatasetAggregation.apply(args=(
        args.task_type,
        domains,
        args.min_agreement_score,
        args.max_examples,
        args.balance_labels,
        args.created_by_id,
        args.license_type,
        args.price,
        None,
        None,
    ))
    payload = result.get(propagate=True)
    print(f"mode=celery payload={payload}")
    return payload


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.mode == "celery":
            run_celery(args)
        else:
            run_direct(args)
    except Exception as exc:
        print(f"Dataset aggregation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
