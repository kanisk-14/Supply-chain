# API Contract (planned)

API base: `/api/v1`. Implemented endpoints are marked **[LIVE]**; the rest are
design-complete contracts for later stages. The OpenAPI schema at `/openapi.json`
reflects whatever is currently mounted and is the authoritative machine-readable
contract.

## Conventions

Every endpoint returns one of three envelopes:

```json
{ "success": true, "data": {}, "message": "Operation successful" }
```

```json
{ "success": true, "data": [], "meta": { "page": 1, "limit": 25, "total": 100, "pages": 4 } }
```

```json
{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "...", "details": [...] } }
```

Pagination defaults: `page=1`, `limit=25`, `max<=100`. Rarely needed when the
resource is not listed.

### Global errors
| HTTP | code | meaning |
|---|---|---|
| 400 | VALIDATION_ERROR | business rule / field-level validation |
| 401 | UNAUTHORIZED | missing/invalid credentials |
| 403 | FORBIDDEN | authenticated but not allowed by role |
| 404 | NOT_FOUND | resource does not exist |
| 409 | CONFLICT | unique-key conflict |
| 409 | INVALID_STATE_TRANSITION | forbidden lifecycle transition |
| 409 | INSUFFICIENT_INVENTORY | allocation exceeds available stock |
| 422 | VALIDATION_ERROR | request body/query fails Pydantic validation |
| 500 | INTERNAL_ERROR | unexpected server error (never leaks internals) |

---

## System

### GET /health **[LIVE]**

Liveness + light database probe.

- **Authorization:** none
- **Response 200:**
```json
{ "success": true, "data": { "status": "ok", "database": "ok", "environment": "development" }, "message": "Health check" }
```
- **Errors:** none (DB outage is reported as `database: "error"`, still 200 and lightweight).

---

## Authentication **[LIVE]**

### POST /api/v1/auth/login
- **Authorization:** none
- **Request:** `{ "email": "...", "password": "..." }`
- **Response 200:** `{ "access_token": "...", "token_type": "bearer" }`
- **Errors:** 401 UNAUTHORIZED on bad credentials; 422 on malformed body.
- **Business rules:** inactive users cannot log in; passwords are verified against `users.password_hash` (hashed, never plaintext).

### GET /api/v1/auth/me
- **Authorization:** Bearer
- **Response 200:** current user (without `password_hash`).
- **Errors:** 401 UNAUTHORIZED.

---

## Users **[LIVE]**

All user endpoints require authentication; writes require `ADMIN` (list/read
view requires any authenticated user).

### GET /api/v1/users
- **Query:** `page`, `limit`, `email` (filter), `role` (filter), `is_active`
- **Response 200:** paged list of users, fields: `id, name, email, role, is_active, created_at, updated_at`.
- **Errors:** 401, 403.

### GET /api/v1/users/{id}
- **Response 200:** single user record. **Errors:** 404 NOT_FOUND, 401.

### POST /api/v1/users
- **Request:** `{ name, email, password, role?, is_active? }` (`role` default `ANALYST`).
- **Response 201:** created user record.
- **Errors:** 400 VALIDATION_ERROR (invalid role/email), 409 CONFLICT (duplicate email).
- **Business rules:** email normalized lower-case; password hashed; never returned.

### PATCH /api/v1/users/{id}
- **Request:** partial `{ name?, email?, password?, role?, is_active? }`.
- **Response 200:** updated record; audit event `USER.UPDATE`.
- **Errors:** 400, 404, 409 CONFLICT (email taken).
- **Business rules:** deactivation via `is_active=false` — users are never hard-deleted.

---

## Suppliers **[LIVE]**

### GET /api/v1/suppliers, GET /api/v1/suppliers/{id}
- **Response:** paged list / single — `id, name, code, contact_name, email, phone, address, is_active, created_at, updated_at`.
- **Errors:** 401, 404.

### POST /api/v1/suppliers
- **Request:** `{ name, code, contact_name?, email?, phone?, address? }`.
- **Errors:** 400, 409 CONFLICT (duplicate code).
- **Business rules:** only master data here — no performance fields are stored or accepted.

### PATCH /api/v1/suppliers/{id}
- **Request:** partial update; **Errors:** 400, 404, 409 (unique `code`).

---

## Products **[LIVE]**

### GET /api/v1/products, GET /api/v1/products/{id}
- **Filters:** `supplier_id`, `sku`, `is_active`, pagination.
- **Response:** `id, supplier_id, sku, name, description, unit, reorder_threshold, is_active`.

### POST /api/v1/products
- **Request:** `{ supplier_id, sku, name, description?, unit?, reorder_threshold? }`.
- **Errors:** 400 (threshold < 0), 404 (unknown supplier), 409 (duplicate sku).

### PATCH /api/v1/products/{id}
- **Request:** partial update; same rules as create.

**Business rules:** `reorder_threshold >= 0`; `sku` unique; deactivation via
`is_active` (existing orders/inventory history intact).

---

## Warehouses **[LIVE]**

### GET /api/v1/warehouses, GET /api/v1/warehouses/{id}, POST /api/v1/warehouses, PATCH /api/v1/warehouses/{id}
- **Request (create):** `{ code, name, address? }`.
- **Errors:** 400, 409 (duplicate code), 404 (read of unknown).

---

## Inventory **[LIVE]**

### GET /api/v1/inventory
- **Filters:** `product_id`, `warehouse_id`, `below_threshold` (bool), pagination.
- **Response:** `id, product_id, warehouse_id, quantity, updated_at` (+ product/warehouse details).

### GET /api/v1/inventory/{id}
- **Response:** one inventory record. **Errors:** 404.

### POST /api/v1/inventory/adjust
- **Authorization:** `WAREHOUSE_MANAGER`, `SUPPLY_CHAIN_MANAGER`, `ADMIN`
- **Request:** `{ product_id, warehouse_id, delta, reason? }`
- **Response 200:** new inventory record + `inventory_transactions` entry.
- **Errors:** 400, 404, 409 INSUFFICIENT_INVENTORY (negative delta exceeding stock).
- **Business rules:** runs in one transaction: lock row `FOR UPDATE`, apply delta, append `ADJUSTMENT` transaction, write audit, write/re-check `LOW_STOCK` alert.

### POST /api/v1/inventory/transfer
- **Authorization:** same as adjust
- **Request:** `{ product_id, from_warehouse_id, to_warehouse_id, quantity }`
- **Response 200:** both warehouse records + `TRANSFER_OUT`/`TRANSFER_IN` entries.
- **Business rules:** atomic; source locked `FOR UPDATE`; `quantity > 0`; insufficient source stock → 409.

### GET /api/v1/inventory/transactions
- **Filters:** `product_id`, `warehouse_id`, `type`, date range, pagination.
- **Business rules:** append-only; returns history, never the live quantity.

---

## Orders

All order endpoints require authentication; state changes require roles.

### GET /api/v1/orders, GET /api/v1/orders/{id}
- **Filters:** `status`, `created_by`, date range, pagination.
- **Response:** order + line items (+ shipments, optional `include_shipments`).

### POST /api/v1/orders
- **Authorization:** `SUPPLY_CHAIN_MANAGER`, `ADMIN`
- **Request:** `{ items: [{ product_id, quantity }] }`
- **Response 201:** order `{ id, order_number, status: "PLACED", items, created_by }`.
- **Errors:** 400 VALIDATION_ERROR (no items / quantity ≤ 0 / duplicate product line), 404 (unknown product).
- **Business rules:** order_number generated server-side; status starts `PLACED`; at least one item; `(order_id, product_id)` unique.

### POST /api/v1/orders/{id}/confirm
- **Transition:** `PLACED → CONFIRMED`. **Errors:** 404, 409 INVALID_STATE_TRANSITION.
- **Business rules:** allocation of stock is a later-stage decision; confirmed orders tracked in audit log.

### POST /api/v1/orders/{id}/fulfill
- **Transition:** `CONFIRMED → FULFILLED`. Only valid from CONFIRMED.
- **Business rules (later stage):** typically reached when the last shipment is DELIVERED.

### POST /api/v1/orders/{id}/cancel
- **Transition:** `PLACED → CANCELLED` or `CONFIRMED → CANCELLED`.
- **Errors:** 404, 409 INVALID_STATE_TRANSITION (FULFILLED cannot be cancelled).

**Business rules:** every transition is validated by `OrderStateMachine`, writes
an audit record, and re-checks related alerts. Clients can never set
`status` directly.

---

## Shipments

### GET /api/v1/shipments, GET /api/v1/shipments/{id}
- **Filters:** `order_id`, `status`, `is_delayed` (derived), date range, pagination.
- **Response:** `id, shipment_number, order_id, status, expected_delivery_at, actual_delivery_at, is_delayed`.

### POST /api/v1/shipments
- **Authorization:** `WAREHOUSE_MANAGER`, `SUPPLY_CHAIN_MANAGER`, `ADMIN`
- **Request:** `{ order_id, expected_delivery_at? }`
- **Response 201:** shipment with `status: "PACKED"`, plus an initial
  `shipment_status_history` row.
- **Errors:** 404 (unknown order), 400 (invalid order state).
- **Business rules:** one order may have many shipments (structural 1:N).

### POST /api/v1/shipments/{id}/dispatch
- **Transition:** `PACKED → IN_TRANSIT`; sets/keeps `expected_delivery_at`.
- **Errors:** 404, 409 INVALID_STATE_TRANSITION.
- **Business rules:** records history; `PACKED → DELIVERED` is never allowed.

### POST /api/v1/shipments/{id}/deliver
- **Transition:** `IN_TRANSIT → DELIVERED`; sets `actual_delivery_at`.
- **Errors:** 404, 409 INVALID_STATE_TRANSITION.
- **Business rules:** `DELIVERED` is terminal; delivery resolves any open
  SHIPMENT_OVERDUE alert for the shipment.

### GET /api/v1/shipments/{id}/history
- **Response:** append-only history rows `{ status, changed_at, changed_by }`.
- **Business rules:** read-only; old rows never mutated.

**Derived state:** `is_delayed = expected_delivery_at < now AND status != DELIVERED`.
Clients cannot set `status = DELAYED` — it is not a persisted value and any such
write is rejected by validation + the state machine.

---

## Alerts (read-only for clients)

### GET /api/v1/alerts
- **Authorization:** any authenticated role (`ALERTS_READ`).
- **Filters:** `type`, `severity`, `entity_type`, `entity_id`, `is_resolved`, pagination.
- **Response (paged):** `{ id, type, severity, entity_type, entity_id, message,
  is_resolved, created_at, resolved_at }`.

### GET /api/v1/alerts/{id}
- **Errors:** 404.

**Business rules:** alerts are derived conditions — a cache of computed state,
never the source of truth. There are no create/update/delete endpoints; clients
cannot set operational conditions through alerts. Rules live:
- `LOW_STOCK`: `inventory.quantity < product.reorder_threshold`, re-evaluated
  reactively after every inventory adjust/transfer/dispatch and resolved once
  every warehouse for the product is back at/above threshold.
- `SHIPMENT_OVERDUE`: `expected_delivery_at < now AND status != DELIVERED`,
  re-evaluated reactively on every shipment create/dispatch/deliver and by the
  scheduled evaluator (`app/jobs/`).

`is_resolved`/`resolved_at` are set automatically when the condition ceases;
a later recurrence creates a fresh alert row (the resolved row is kept as
history). Alerts are never manually resolved by clients.

---

## Analytics (computed live)

All require `ANALYST` (or ADMIN) via `ANALYTICS_READ`; every other role can also
read them. `period` ∈ {day, week, month}; `days` ∈ [1, 365].

| endpoint | purpose |
|---|---|
| GET /api/v1/analytics/overview | global KPIs (products, stock, low stock, active orders, in-transit, delayed) |
| GET /api/v1/analytics/inventory | total/low stock, distribution by warehouse & product, movement trends |
| GET /api/v1/analytics/shipments | delivered/delayed aggregates, avg delivery & delay hours, delivery performance |
| GET /api/v1/analytics/suppliers | computed supplier performance from orders/shipments |
| GET /api/v1/analytics/bottlenecks | time per lifecycle stage (confirm→packed, packed→transit, transit→delivered) |

**Business rules:** every value is computed live via SQL aggregation over the
operational tables — no KPI is stored (no analytics tables). Bottleneck stages
and percentiles are computed with MySQL window functions
(`LAG`/`ROW_NUMBER`/`PERCENT_RANK`) over `shipment_status_history` +
`audit_logs`. Derived definitions used throughout:
- on time: `expected IS NULL OR actual_delivery_at <= expected_delivery_at`
- delayed: `expected_delivery_at < now AND status != DELIVERED`
- avg delivery = `mean(actual_delivery_at - created_at)` over delivered shipments;
  avg delay = `mean(actual_delivery_at - expected_delivery_at)` over late ones.

ML models are explicitly future scope and are never part of the transactional
schema.