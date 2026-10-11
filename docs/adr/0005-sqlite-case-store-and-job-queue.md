# 0005. SQLite for cases and the job queue, one worker

- Status: Accepted
- Date: 2026-10-06

## Context
Processing a case takes about 30 seconds of model time, so it cannot happen inside an HTTP request. Cases, decisions, and the audit trail must survive restarts. The whole system runs on one laptop, built by one person, and should start with one command.

## Options considered
- **Postgres + Celery + Redis.** The standard production stack; three extra services to run and configure.
- **FastAPI background tasks.** No extra services, but jobs are lost on restart.
- **SQLite for data and the job queue, one worker process** that claims jobs with a lease.

## Decision
SQLite (via SQLAlchemy 2.0) holds cases, jobs, case events, and decisions. One worker claims the oldest queued job, marks it running with a lease, and requeues expired leases on start. One worker also guarantees the GPU runs one model job at a time.

## Consequences
- One writer at a time. That is fine for a desk handling hundreds of cases a day, and not for thousands per minute.
- Moving to Postgres later is a connection-string change plus a migration, because the code uses SQLAlchemy rather than raw SQLite.
- No extra services: Qdrant is the only container.
