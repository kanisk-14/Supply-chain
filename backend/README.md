# Supply Chain Tracking & Analytics Systems

Production-style backend for a supply-chain tracking and analytics system.
**Stage 1** shipped the foundation: API conventions, database schema,
migrations, error handling, response envelope, health endpoint, state machines,
and the testing base. **Stage 2** ships JWT authentication + RBAC, the
Users/Suppliers/Products/Warehouses resource APIs, transactional inventory
(adjust/transfer + append-only history), LOW_STOCK alerts, audit logging, a
development seed script, and full endpoint test coverage.

## Stack

- Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic
- MySQL 8+ / InnoDB (`DATETIME(6)`, native ENUMs, UTF-8mb4)
- PyMySQL driver, PyJWT, bcrypt, email-validator, pytest + httpx

## Project structure

```
backend/
├── app/
│   ├── main.py                 # app factory, CORS, exception handlers, /health
│   ├── core/                   # config, database (Base/engine/session), security
│   ├── common/                 # exceptions, response envelopes, pagination, handlers
│   ├── modules/<domain>/       # users, suppliers, products, warehouses, inventory,
│   │                           # orders, shipments, alerts, audit_logs, analytics
│   ├── state_machines/         # base FSM + order + shipment definitions
│   └── jobs/                   # reserved for scheduled evaluators (later stage)
├── alembic/                    # migrations (env.py + versions/)
├── tests/                      # unit + integration (pytest)
├── docs/                       # ERD, DATABASE, ARCHITECTURE, API_CONTRACT
└── requirements.txt
```

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit DATABASE_URL / TEST_DATABASE_URL etc.
alembic upgrade head        # create the canonical schema
python -m app.seed          # optional: dev users, suppliers, products, stock
```

The bundled `alembic/env.py` reads `DATABASE_URL` from `.env`; `alembic.ini`
does not hardcode credentials.

## Run

```bash
uvicorn app.main:app --reload
```

- Health check: `GET /health`
- OpenAPI: `http://127.0.0.1:8000/docs` (and `/redoc`, `/openapi.json`)
- Login: `POST /api/v1/auth/login` with a seeded account (e.g. `admin@example.com / Admin123!`)

## Tests

```bash
pytest -v
```

Database-backed tests run only when MySQL is reachable and skip otherwise.
They use `TEST_DATABASE_URL` and never touch the dev database.

## Documentation

- `docs/ERD.md` — entity-relationship model
- `docs/DATABASE.md` — canonical schema, constraints, indexes
- `docs/ARCHITECTURE.md` — request lifecycle, layers, transactions, state machines
- `docs/API_CONTRACT.md` — API surface; implemented endpoints are marked **[LIVE]**

## Non-goals

No orders/shipments workflows, no alert scheduler, no analytics, no ML, no
frontend. The layers are designed so those attach without architectural rewrites.