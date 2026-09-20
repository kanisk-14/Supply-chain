# Architecture

## Request lifecycle

Every request flows through a fixed pipeline. Each layer has a single
responsibility; business logic never leaks upward into routers.

```
Request
  ↓
Router                                   URLs → handlers only
  ↓
Middleware / Dependencies                CORS, auth (later), RBAC (later),
                                         request context, common validation
  ↓
Controller / Route Handler               HTTP request ↔ service call translation
  ↓
Service                                  business rules, state transitions,
                                         transaction orchestration, alert side effects
  ↓
Repository / DAL                         the ONLY layer that talks to MySQL
  ↓
MySQL
  ↓
Consistent Response                      envelope builders / global exception handlers
```

## Layer responsibilities

| layer | owns | rejects |
|---|---|---|
| Router | URL mapping, path/query parameter extraction | business logic |
| Middleware / dependencies | CORS, authentication, role checks, request context | domain decisions |
| Controller | translating HTTP input to service input and service output to the envelope | business rules |
| Service | state machines, transactional workflows, inventory/order/shipment rules, alert triggers | raw SQL, HTTP concerns |
| Repository | SQLAlchemy queries against models | business rules, HTTP concerns |
| Database | MySQL/InnoDB source of truth | computed/derived state |

Two enforcement rules from the spec, encoded here:

- **No raw SQL in services.** Only the repository layer constructs queries.
- **No SQLAlchemy model access in routes.** Routes talk to services.

Stage 1 ships the pipeline's shared machinery (envelope, error handling,
pagination, session dependency, state machines); resource routers/services land
in later stages.

## Response envelope & errors

- Success: `{"success": true, "data": ..., "message": ...}`
- Collections: `{"success": true, "data": [...], "meta": {page, limit, total, pages}, ...}`
- Error: `{"success": false, "error": {code, message, details?}}`

All controllers emit the same envelope via `app/common/responses.py`. All errors
flow through the global handlers in `app/common/handlers.py`; no route formats an
error ad hoc.

| exception | HTTP | code |
|---|---|---|
| `NotFoundError` | 404 | NOT_FOUND |
| `ValidationError` | 400 | VALIDATION_ERROR |
| `ConflictError` | 409 | CONFLICT |
| `UnauthorizedError` | 401 | UNAUTHORIZED |
| `ForbiddenError` | 403 | FORBIDDEN |
| `InvalidStateTransitionError` | 409 | INVALID_STATE_TRANSITION |
| `InsufficientInventoryError` | 409 | INSUFFICIENT_INVENTORY |
| FastAPI/Pydantic request validation | 422 | VALIDATION_ERROR |
| unhandled `Exception` | 500 | INTERNAL_ERROR (stack logged server-side, never sent) |

Request-validation errors log nothing and include only JSON-safe structured
details (field/message/type), never exception objects.

## Pagination

Default `page=1`, `limit=25`, `max_limit=100` (`app/common/pagination.py`).
`0`/`None` mean "use the default"; negatives clamp to the floor; oversized
limits clamp to 100. Future collection endpoints use the helper to compute
paged selects and `meta`.

## Naming and versioning

- API prefix: `/api/v1` (`API_PREFIX` in `app/main.py`).
- All resource routers (auth, users, suppliers, products, warehouses,
  inventory, orders, shipments, alerts, analytics) mount below the prefix.
- OpenAPI is discoverable at `/openapi.json`, `/docs`, `/redoc`.

## Transaction boundaries

The **service layer** owns transactions. Repositories receive a `Session` and
must never commit. A write workflow has this shape:

```
session.begin()
  ↓
lock relevant rows (SELECT ... FOR UPDATE)
  ↓
validate business rule (state machine / stock check)
  ↓
modify operational state
  ↓
write history row (inventory_transactions / shipment_status_history)
  ↓
write audit_log entry
  ↓
re-evaluate and write derived alerts
  ↓
commit
(any failure → rollback; no partial updates)
```

The health endpoint's `SELECT 1` probe is the single deliberate exception to the
"no DB access outside repositories" rule: it touches no business data.

## Concurrency

Inventory mutations never do a blind read-modify-write. Writes inside a
transaction use `SELECT ... FOR UPDATE` (row lock) on the affected
`(product, warehouse)` rows before computing the new quantity. The
`UNIQUE(product_id, warehouse_id)` constraint protects against two writers
creating the same row; an `IntegrityError` on insert is handled as a retry or a
`ConflictError`. Services choose the required isolation/locking explicitly per
operation — this is where future allocation logic will live.

## State machines

`app/state_machines/` defines pure, dependency-free finite state machines. They
never persist anything; the service layer does.

```
Order:
  PLACED → CONFIRMED → FULFILLED
     ↓
  CANCELLED

  PLACED→CONFIRMED, PLACED→CANCELLED,
  CONFIRMED→FULFILLED, CONFIRMED→CANCELLED          (valid)
  everything else, incl. terminal self-transitions   (invalid → 409)

Shipment:
  PACKED → IN_TRANSIT → DELIVERED
  PACKED→IN_TRANSIT, IN_TRANSIT→DELIVERED            (valid)
  PACKED→DELIVERED is deliberately NOT supported
  DELAYED is NOT a state — derived only:
      is_delayed = expected_delivery_at < now AND status != DELIVERED
```

Unit tests lock the specifications in (`tests/unit/test_state_machines.py`).

## Source-of-truth rules

| fact | lives in |
|---|---|
| product master data | `products` |
| current stock (product × warehouse) | `inventory` |
| stock movement history | `inventory_transactions` |
| order lifecycle | `orders` + `order_items` |
| shipment lifecycle | `shipments` |
| shipment transition history | `shipment_status_history` |
| supplier master data | `suppliers` |
| who changed what | `audit_logs` |
| computed views | analytics — computed live, never stored |
| derived conditions | `alerts` (read-only to clients) |

No fact is duplicated as authoritative data in two tables. Analytics and alerts
are always *derived* from operational tables, never written back into them as
authoritative state.

## Analytics principles (live)

- Queries read operational tables only; nothing analytic is stored as facts
  (there are no analytics/KPI tables).
- All aggregation (overview, inventory distribution, movement trends, delivery
  performance, supplier performance, bottleneck timings) runs in SQL:
  window functions (`LAG` for stage pairing, `ROW_NUMBER` for first-PACKED,
  `PERCENT_RANK` for p50/p90) over `shipment_status_history` and `audit_logs`;
  conditional `CASE`-inside-aggregate (MySQL has no `FILTER`) for on-time/late
  and distinct-conditioned counts.
- Python (`AnalyticsRepository` → `AnalyticsService`) only formats results into
  JSON-safe units (hours, on-time rates) and builds the bottleneck report.
- `suppliers` holds no performance fields; performance is computed from
  orders/shipments/history at read time.

## Alert principles (live)

- Alerts are produced from operational conditions: reactively on every write
  path that can change the condition (inventory adjust/transfer/dispatch →
  `LOW_STOCK`; shipment create/dispatch/deliver → `SHIPMENT_OVERDUE`), plus a
  scheduled evaluator in `app/jobs/` for time-based conditions that flip
  without a write (a shipment merely passing its expected delivery time).
- The scheduled evaluator reconciles only the union of (potentially overdue
  shipments) and (shipments behind unresolved overdue alerts) — it never
  re-evaluates the whole table. It runs as `python -m app.jobs.scheduler`, or
  in-app when `SCHEDULER_ENABLED=true` (`SCHEDULER_INTERVAL_SECONDS`, default
  300). No Celery/Redis.
- Alerts never become the source of truth for inventory or shipment state.
- The alerts API is read-only (`ALERTS_READ`); clients can list/get alerts but
  can never set conditions or statuses (`status = DELAYED` is never persisted).

## Configuration

Everything comes from environment (`.env` via `pydantic-settings`); `config.py`
validates values eagerly so bad configuration fails at startup. CORS origins
are an explicit allow-list from `CORS_ORIGINS` — `*` is never allowed in
production. `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` are
already wired into settings so Stage 2 auth does not change the config surface.