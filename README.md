# AI Data Marketplace Backend

This is the backend repository for the AI Data Marketplace and Crowdsourcing Platform for Amharic Dataset Collection.

## Architecture

This project strictly adheres to modular domain-driven application patterns.

- **`config/`**: Contains core Django configurations, settings, URLs mapping, and routing.
- **`apps/`**: The core domains of the platform.
- **`core/`**: Abstractions and cross-cutting concerns (authentication, permissions, constants).

## Getting Started

1. Set up a virtual environment: `python -m venv venv`
2. Activate and install dev dependencies: `pip install -r requirements/dev.txt`
3. Make a copy of `.env` and fill it in.
4. Run migrations: `bash scripts/migrate.sh`
5. Run server: `bash scripts/runserver.sh`

## Processing Smoke Test

To test the document preprocessing pipeline without a Celery worker, run:

```powershell
c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_processing_pipeline.py <raw_document_id>
```

To exercise the Celery task locally in-process:

```powershell
c:/Users/aman/Desktop/fidelai-backend/venv/Scripts/python.exe scripts/run_processing_pipeline.py <raw_document_id> --mode celery
```

## Scheduled Processing

For production-style operation, use Celery worker + beat. Beat will run
`DispatchPendingDocumentProcessing` every minute, which scans
`RawDocument.processing_status = pending` and enqueues
`DocumentProcessingPipeline(<raw_document_id>)` tasks.

Environment variable:

- `CELERY_PROCESSING_BATCH_SIZE` (default: `25`) controls how many pending docs
	are queued per beat tick.
