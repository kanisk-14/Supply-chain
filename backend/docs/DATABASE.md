# Database Schema (canonical)

One canonical schema. The ORM models in `app/modules/*/models.py` are the source
of truth; the Alembic migration under `alembic/versions/` is generated from them
and therefore always reflects the same schema. Do not hand-edit one side without
the other.

Engine: MySQL 8+ / InnoDB, character set `utf8mb4` collation
`utf8mb4_0900_ai_ci`. Primary keys are `BIGINT AUTO_INCREMENT`. All timestamps
are `DATETIME(6)` (fractional seconds) and are stored as naive UTC.

## Delete policy

Operational history is never cascaded. Every foreign key is `ON DELETE
RESTRICT`; "deleting" master data is done by flipping `is_active = 0`. This
preserves historical records (orders, transactions, histories, audit trails)
even when entities are deactivated.

## Tables

### users
| column | type | notes |
|---|---|---|
| id | BIGINT PK | |
| name | VARCHAR(120) NOT NULL | |
| email | VARCHAR(255) NOT NULL | UNIQUE + index |
| password_hash | VARCHAR(255) NOT NULL | never plaintext |
| role | ENUM(ADMIN, WAREHOUSE_MANAGER, SUPPLY_CHAIN_MANAGER, ANALYST) NOT NULL | default ANALYST |
| is_active | BOOL NOT NULL | default 1 |
| created_at / updated_at | DATETIME(6) NOT NULL | |

### suppliers
`id` PK · `name VARCHAR(120)` NN · `code VARCHAR(32)` NN **UNIQUE** · `contact_name/email/phone/address` nullable · `is_active` NN · timestamps.

No supplier-performance fields: performance is computed from orders/shipments, never stored as authoritative data.

### products
`id` PK · `supplier_id` **FK → suppliers.id** (RESTRICT) · `sku VARCHAR(64)` NN **UNIQUE** · `name VARCHAR(120)` NN · `description TEXT` · `unit VARCHAR(24)` NN · `reorder_threshold NUMERIC(12,4)` NN default 0 **CHECK ≥ 0** · `is_active` NN · timestamps. Supplier 1—N products.

### warehouses
`id` PK · `code VARCHAR(32)` NN **UNIQUE** · `name VARCHAR(120)` NN · `address VARCHAR(255)` · `is_active` NN · timestamps.

### inventory — *current state*
`id` PK · `product_id` **FK → products.id** · `warehouse_id` **FK → warehouses.id** · `quantity NUMERIC(12,4)` NN default 0 **CHECK ≥ 0** · timestamps.
**UNIQUE(product_id, warehouse_id)**.
A stock record is always `(product, warehouse, quantity)`; it is never a property of the product alone.

### inventory_transactions — *append-only history*
`id` PK · `product_id` FK · `warehouse_id` FK · `type` ENUM(RECEIPT, ORDER_ALLOCATION, SHIPMENT_DISPATCH, ADJUSTMENT, TRANSFER_IN, TRANSFER_OUT) · `quantity NUMERIC(12,4)` NN **CHECK ≠ 0 (signed)** · `reference_type VARCHAR(32)` · `reference_id BIGINT` · `created_by` **FK → users.id** · `created_at`.
Positive = stock-in, negative = stock-out. `reference_type/reference_id` is a polymorphic provenance pointer (e.g. ORDER/12, SHIPMENT/5, ADJUSTMENT, TRANSFER, SUPPLIER, MANUAL). Never used as the live inventory snapshot.

### orders
`id` PK · `order_number VARCHAR(32)` NN **UNIQUE** · `status` ENUM(PLACED, CONFIRMED, FULFILLED, CANCELLED) NN default PLACED · `created_by` **FK → users.id** · timestamps.

### order_items
`id` PK · `order_id` **FK → orders.id** · `product_id` **FK → products.id** · `quantity NUMERIC(12,4)` NN **CHECK > 0** · **UNIQUE(order_id, product_id)**.
An order must always have ≥ 1 item (enforced in the service layer).

### shipments
`id` PK · `shipment_number VARCHAR(32)` NN **UNIQUE** · `order_id` **FK → orders.id** · `status` ENUM(PACKED, IN_TRANSIT, DELIVERED) NN default PACKED · `expected_delivery_at DATETIME(6)` · `actual_delivery_at DATETIME(6)` · `created_by` **FK → users.id** · timestamps.
One order —N shipments (structural 1:N). **DELAYED is not a column/state**: a shipment is *derived* delayed when `expected_delivery_at < now AND status != DELIVERED`.

### shipment_status_history — *append-only*
`id` PK · `shipment_id` **FK → shipments.id** · `status` ENUM(PACKED, IN_TRANSIT, DELIVERED) NN · `changed_at DATETIME(6)` NN · `changed_by` **FK → users.id** NN.
One row per legitimate transition. Existing rows are never updated; it answers "what happened to this shipment?".

### alerts — *derived conditions*
`id` PK · `type` ENUM(LOW_STOCK, SHIPMENT_OVERDUE) · `severity` ENUM(INFO, WARNING, CRITICAL) · `entity_type VARCHAR(32)` · `entity_id BIGINT` · `message VARCHAR(255)` · `is_resolved BOOL` NN default 0 · `created_at` · `resolved_at DATETIME(6)`.
Polymorphic reference (no FK): `entity_type ∈ {product, shipment}` depending on `type`. Alerts are a derived cache of operational conditions, never the source of truth.

### audit_logs — *who changed what*
`id` PK · `user_id` **FK → users.id** · `action VARCHAR(64)` · `entity_type VARCHAR(32)` · `entity_id BIGINT` · `old_value JSON` · `new_value JSON` · `created_at`.
Polymorphic entity reference; old/new values captured as JSON.

## Indexes

| table | index | purpose |
|---|---|---|
| users | UNIQUE(email) | login + de-dup |
| suppliers | UNIQUE(code) | natural key |
| products | UNIQUE(sku), idx(supplier_id) | lookups |
| warehouses | UNIQUE(code) | natural key |
| inventory | UNIQUE(product_id, warehouse_id), idx(warehouse_id) | composite covers product_id alone; separate index serves warehouse-side lookups |
| orders | UNIQUE(order_number), idx(status), idx(created_at) | lifecycle + lists |
| order_items | idx(order_id), idx(product_id) | lookups |
| shipments | UNIQUE(shipment_number), idx(order_id), idx(status), idx(expected_delivery_at) | lifecycle + overdue scans |
| shipment_status_history | idx(shipment_id), idx(changed_at) | timeline queries |
| inventory_transactions | idx(product_id), idx(warehouse_id), idx(created_at), idx(reference_type, reference_id) | history queries |
| audit_logs | idx(user_id), idx(entity_type, entity_id), idx(created_at) | accountability queries |
| alerts | idx(type, is_resolved), idx(entity_type, entity_id) | list + entity drill-downs |

Deliberately omitted: the singleton-column `inventory.product_id` index (the
UNIQUE composite already covers that prefix) and separate single-column alerts
indexes (the composites cover the query shapes above).

## Migrations

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic downgrade -1     # validated in this repo: drops tables in FK-safe order
```

`alembic/env.py` imports every model module so autogenerate always sees the full
metadata, and reads the URL from `DATABASE_URL` (never `alembic.ini`).