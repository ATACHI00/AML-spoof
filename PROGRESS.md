# AML Monitor — Progress Tracking

## Overview

AML Monitor — платформа мониторинга транзакций для выявления отмывания денег (AML).
MVP для pilot-клиентов: небольшие финтех-компании, необанки, платёжные сервисы.

## Stages

### ✅ Stage 0 — Project Skeleton (COMPLETED)

**Что сделано:**
- [x] Docker Compose: PostgreSQL 16 + Redis 7 + FastAPI + Celery Worker + Next.js
- [x] Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 async, Poetry, Ruff
- [x] Модели данных (8 сущностей): Client, Account, Transaction, Alert, Case, AuditLog, Rule, SanctionsList
- [x] Alembic миграции (initial schema с ENUMs, индексами, внешними ключами)
- [x] API: healthcheck (DB/Redis/Celery), API-key auth, placeholder для v1
- [x] Celery конфигурация с task definitions
- [x] Hash chain для audit_log (tamper-evidence)
- [x] Idempotency через external_id UNIQUE constraint
- [x] Тесты: healthcheck, модели, hash chain integrity
- [x] Frontend: Next.js 14 (App Router), TypeScript, dashboard с system status
- [x] CI: GitHub Actions (ruff, mypy, pytest, frontend lint)
- [x] Документация: README.md, PROGRESS.md

### ✅ Stage 1 — Transaction Ingestion (COMPLETED)

- [x] REST endpoint: POST /api/v1/transactions (idempotent via external_id)
- [x] CSV batch import endpoint (POST /api/v1/transactions/batch)
- [x] Schema validation (Pydantic TransactionCreate/TransactionResponse)
- [x] Celery task for async processing (process_transaction.delay)
- [x] Idempotency handling (external_id UNIQUE, returns 200 on duplicate)
- [x] Account resolution (source/destination account_number → UUID)
- [x] Error handling (unknown account → 422, missing API key → 401)
- [x] Tests: 8 tests covering success, idempotency, errors, batch, list

### ✅ Stage 2 — Rule Engine (COMPLETED)

- [x] 6 rule-based detectors (configurable thresholds):
  - **structuring** — smurfing patterns (multiple txns below threshold)
  - **rapid_movement** — in-and-out fund movement within short window
  - **round_amount** — unusually round amounts or just-below-threshold
  - **velocity** — high transaction frequency per time window
  - **geographic** — high-risk jurisdictions/channels (crypto)
  - **dormant** — activity on accounts inactive for 90+ days
- [x] Detector registry (`DETECTOR_REGISTRY`) for extensibility
- [x] `run_rule_engine()` orchestrator — runs all active rules, creates alerts
- [x] Alert generation pipeline (severity, risk_score, title, description)
- [x] Celery task `process_transaction` updated to invoke rule engine
- [x] CRUD API for rules: `GET/POST /api/v1/rules`, `GET/PUT/DELETE /api/v1/rules/{id}`
- [x] Pydantic schemas: `RuleCreate`, `RuleUpdate`, `RuleResponse`, `RuleListResponse`
- [x] Alembic migration `0002_seed_default_rules` — 6 default rules with configs
- [x] Unit tests: 20 tests covering all detectors, registry, engine, persistence

### ✅ Stage 3 — Case Management UI (COMPLETED)

- [x] Backend: `GET /api/v1/alerts/` — paginated list with filters (status, severity, rule_id)
- [x] Backend: `GET /api/v1/alerts/{id}` — alert detail view
- [x] Backend: `PATCH /api/v1/alerts/{id}/status` — close/escalate/in_review with mandatory comment
- [x] Backend: Audit log integration — immutable hash chain on every status change
- [x] Backend: Pydantic schemas (`AlertResponse`, `AlertListResponse`, `AlertStatusUpdate`)
- [x] Backend: Alert service with `list_alerts()`, `get_alert_by_id()`, `update_alert_status()`
- [x] Backend: 16 tests covering listing, filtering, pagination, detail, status updates, hash chain integrity
- [x] Frontend: `/alerts` — alert list page with status/severity filters and pagination
- [x] Frontend: `/alerts/[id]` — alert detail page with status badges and action buttons
- [x] Frontend: Modal dialog for close/escalate/in_review with mandatory comment
- [x] Frontend: API client module (`api.ts`) with typed interfaces
- [x] All 59 backend tests passing
- [x] Frontend builds successfully (Next.js 14)

### ✅ Stage 4 — Sanctions Screening (COMPLETED)

- [x] Fuzzy name matching: Levenshtein distance, Jaro-Winkler similarity, name normalisation
- [x] OFAC SDN list downloader & CSV parser (zip support, alias extraction)
- [x] Sanctions screening service (`screen_name_against_sanctions`, `screen_transaction_parties`)
- [x] Sanctions list management: list, search, stats
- [x] REST API: `POST /api/v1/sanctions/screen`, `GET /api/v1/sanctions/entries`, `GET /api/v1/sanctions/stats`, `POST /api/v1/sanctions/import`
- [x] New rule engine detector `sanctions_match` — screens transaction parties via `extra_data` or client names
- [x] Alembic migration `0003_seed_sanctions_rule` — default sanctions_match rule (weight 2.0)
- [x] Pydantic schemas: `SanctionsScreenRequest/Result`, `SanctionsEntryResponse`, `SanctionsStatsResponse`, `SanctionsImportResponse`
- [x] Tests: 67 new tests (fuzzy matching, provider parser, screening service, API endpoints)
- [x] All 126 backend tests passing

### ✅ Stage 5 — ML Scoring (COMPLETED)

- [x] Feature engineering (26 features: amount, temporal, velocity, account, client, channel/currency)
- [x] Isolation Forest model with lazy training on historical data
- [x] SHAP explainability — top 10 feature contributors per alert
- [x] ML anomaly detector integrated into rule engine (`ml_anomaly` detector type)
- [x] REST API: `GET /api/v1/ml/model`, `POST /api/v1/ml/train`, `POST /api/v1/ml/score`, `POST /api/v1/ml/features`
- [x] Model serialization/deserialization for caching
- [x] Alembic migration `0004_seed_ml_rule` — default ML rule (weight 1.5, threshold 0.5)
- [x] Tests: 23 new tests (feature engineering, ML scorer, detector integration, API endpoints)
- [x] All 149 backend tests passing

### ✅ Stage 6 — Graph Analysis (COMPLETED)

- [x] Transaction graph construction — directed weighted graph (account → account)
- [x] Cycle detection — DFS-based with configurable max length and min volume
- [x] Suspicious cluster detection — BFS connected components with density scoring
- [x] REST API: `POST /api/v1/graph/analyze`, `GET /api/v1/graph/cycles`, `GET /api/v1/graph/clusters`, `GET /api/v1/graph/edges`
- [x] New rule engine detector `graph_anomaly` — screens transactions for cycle/cluster involvement
- [x] Alembic migration `0005_seed_graph_rule` — default graph_anomaly rule (weight 1.5)
- [x] Alembic migration `0006_add_graph_detector_type` — extended ENUM with graph_anomaly
- [x] Tests: 31 new tests (graph construction, cycle detection, cluster detection, API, rule engine integration)

### ✅ Stage 7 — Audit & Compliance Reporting (COMPLETED)

- [x] Audit log viewer API: `GET /api/v1/audit/logs` (paginated, filterable), `GET /api/v1/audit/logs/{id}`
- [x] Hash chain verification endpoint: `GET /api/v1/audit/verify` — tamper-evidence check
- [x] SAR-like CSV export: `GET /api/v1/compliance/export/alerts.csv` (filterable by status/severity)
- [x] SAR text report: `GET /api/v1/compliance/export/alert/{id}/report` — human-readable SAR
- [x] Compliance dashboard stats: `GET /api/v1/compliance/stats` — alerts by severity/status, cases, transactions
- [x] Frontend: `/compliance` — compliance dashboard with stats cards, severity/status breakdown, audit log viewer, hash chain verification, CSV export links
- [x] Tests: 18 new tests (audit log API, compliance stats, CSV export, SAR report, hash chain verification)

## How to Run

```bash
# Copy environment config
cp .env.example .env

# Start all services
docker compose up --build

# Access:
# - Frontend: http://localhost:3000
# - API: http://localhost:8000
# - Swagger docs: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 16 |
| Cache/Queue | Redis 7 + Celery |
| Frontend | Next.js 14, TypeScript |
| Infra | Docker Compose |
| Linter | Ruff |
| Tests | pytest, pytest-asyncio |
| CI | GitHub Actions |