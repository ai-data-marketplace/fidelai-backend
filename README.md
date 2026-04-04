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
