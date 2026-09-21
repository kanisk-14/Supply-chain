"""Centralized role → permission mapping and checks.

Every endpoint authorizes itself by declaring the permissions it needs. The
allowed permissions per role are defined exactly once here so a role change is a
single edit and roles can never silently drift apart.

Permission coverage by role:

- ADMIN — everything.
- WAREHOUSE_MANAGER — warehouse/inventory operations scoped to assigned warehouse;
  relevant orders/shipments; relevant warehouse/inventory alerts.
- SUPPLY_CHAIN_MANAGER — suppliers, products, orders, shipments; inventory
  visibility (read); supply-chain analytics; relevant alerts.
- ANALYST — read-only analytics/reporting; relevant inventory/shipment/supplier/
  alert data; NO operational mutations.

Users are the exception: creating/updating users (including assigning roles) is
ADMIN-only, so no user can grant themselves a higher role.
"""

from __future__ import annotations

from enum import Enum

from app.common.exceptions import ForbiddenError
from app.modules.users.models import UserRole


class Permission(str, Enum):
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    SUPPLIERS_READ = "suppliers:read"
    SUPPLIERS_WRITE = "suppliers:write"
    PRODUCTS_READ = "products:read"
    PRODUCTS_WRITE = "products:write"
    WAREHOUSES_READ = "warehouses:read"
    WAREHOUSES_WRITE = "warehouses:write"
    INVENTORY_READ = "inventory:read"
    INVENTORY_WRITE = "inventory:write"
    INVENTORY_TRANSACTIONS_READ = "inventory:transactions:read"
    ORDERS_READ = "orders:read"
    ORDERS_WRITE = "orders:write"
    SHIPMENTS_READ = "shipments:read"
    SHIPMENTS_WRITE = "shipments:write"
    ANALYTICS_READ = "analytics:read"
    ALERTS_READ = "alerts:read"


_ALL_PERMISSIONS = set(Permission)

ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.ADMIN: _ALL_PERMISSIONS,
    UserRole.WAREHOUSE_MANAGER: {
        Permission.WAREHOUSES_READ,
        Permission.WAREHOUSES_WRITE,
        Permission.INVENTORY_READ,
        Permission.INVENTORY_WRITE,
        Permission.INVENTORY_TRANSACTIONS_READ,
        Permission.ORDERS_READ,
        Permission.SHIPMENTS_READ,
        Permission.SHIPMENTS_WRITE,
        Permission.ALERTS_READ,
    },
    UserRole.SUPPLY_CHAIN_MANAGER: {
        Permission.SUPPLIERS_READ,
        Permission.SUPPLIERS_WRITE,
        Permission.PRODUCTS_READ,
        Permission.PRODUCTS_WRITE,
        Permission.WAREHOUSES_READ,
        Permission.INVENTORY_READ,
        Permission.INVENTORY_WRITE,
        Permission.INVENTORY_TRANSACTIONS_READ,
        Permission.ORDERS_READ,
        Permission.ORDERS_WRITE,
        Permission.SHIPMENTS_READ,
        Permission.SHIPMENTS_WRITE,
        Permission.ANALYTICS_READ,
        Permission.ALERTS_READ,
    },
    UserRole.ANALYST: {
        Permission.ANALYTICS_READ,
        Permission.INVENTORY_READ,
        Permission.SHIPMENTS_READ,
        Permission.SUPPLIERS_READ,
        Permission.ALERTS_READ,
    },
}


def has_permissions(role: UserRole, *permissions: Permission) -> bool:
    """True when ``role`` has all of the requested permissions."""
    granted = ROLE_PERMISSIONS.get(role, set())
    return all(permission in granted for permission in permissions)


def require_permissions(*permissions: Permission):
    """Build a FastAPI dependency that rejects callers lacking the permissions.

    Deliberately requires *all* listed permissions (no partial granting).
    """

    def dependency(user) -> None:
        if not has_permissions(user.role, *permissions):
            needed = ", ".join(p.value for p in permissions)
            raise ForbiddenError(
                f"Role {user.role.value} is not allowed to perform "
                f"this action (requires {needed})"
            )

    return dependency