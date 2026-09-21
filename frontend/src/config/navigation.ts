"use client";

import { UserRole, Permission } from "@/types/api";
import {
  LayoutDashboard,
  Boxes,
  ShoppingCart,
  Truck,
  Package,
  Building2,
  Warehouse,
  AlertTriangle,
  BarChart2,
  Users,
} from "lucide-react";

export interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  requiredPermissions?: Permission[];
  requiredRoles?: UserRole[];
  adminOnly?: boolean;
}

export interface NavSection {
  label?: string;
  items: NavItem[];
}

export const NAVIGATION_CONFIG: NavSection[] = [
  {
    items: [
      {
        name: "Dashboard",
        href: "/",
        icon: LayoutDashboard,
        // Visible to every authenticated role; the dashboard itself is role-specific.
      },
    ],
  },
  {
    label: "Operations",
    items: [
      {
        name: "Inventory",
        href: "/inventory",
        icon: Boxes,
        requiredPermissions: ["inventory:read"],
      },
      {
        name: "Orders",
        href: "/orders",
        icon: ShoppingCart,
        requiredPermissions: ["orders:read"],
      },
      {
        name: "Shipments",
        href: "/shipments",
        icon: Truck,
        requiredPermissions: ["shipments:read"],
      },
    ],
  },
  {
    label: "Catalog",
    items: [
      {
        name: "Products",
        href: "/products",
        icon: Package,
        requiredPermissions: ["products:read"],
      },
      {
        name: "Suppliers",
        href: "/suppliers",
        icon: Building2,
        requiredPermissions: ["suppliers:read"],
      },
      {
        name: "Warehouses",
        href: "/warehouses",
        icon: Warehouse,
        requiredPermissions: ["warehouses:read"],
        // SUPPLY_CHAIN_MANAGER has warehouses:read on the API but the role
        // spec excludes the Warehouses module from its sidebar.
        requiredRoles: ["ADMIN", "WAREHOUSE_MANAGER"],
      },
    ],
  },
  {
    label: "Insights",
    items: [
      {
        name: "Alerts",
        href: "/alerts",
        icon: AlertTriangle,
        requiredPermissions: ["alerts:read"],
      },
      {
        name: "Analytics",
        href: "/analytics",
        icon: BarChart2,
        requiredPermissions: ["analytics:read"],
        requiredRoles: ["ADMIN", "SUPPLY_CHAIN_MANAGER", "ANALYST"],
      },
    ],
  },
  {
    label: "Administration",
    items: [
      {
        name: "User Management",
        href: "/admin/users",
        icon: Users,
        requiredPermissions: ["users:read"],
        adminOnly: true,
      },
    ],
  },
];

// Mirrors backend/app/modules/auth/permissions.py ROLE_PERMISSIONS exactly.
// Only ADMIN holds users:read/users:write. Do not widen these without a
// matching backend change or the UI will render modules that 403.
export const ROLE_PERMISSIONS: Record<UserRole, Permission[]> = {
  ADMIN: [
    "users:read",
    "users:write",
    "suppliers:read",
    "suppliers:write",
    "products:read",
    "products:write",
    "warehouses:read",
    "warehouses:write",
    "inventory:read",
    "inventory:write",
    "inventory:transactions:read",
    "orders:read",
    "orders:write",
    "shipments:read",
    "shipments:write",
    "analytics:read",
    "alerts:read",
  ],
  WAREHOUSE_MANAGER: [
    "warehouses:read",
    "warehouses:write",
    "inventory:read",
    "inventory:write",
    "inventory:transactions:read",
    "orders:read",
    "shipments:read",
    "shipments:write",
    "alerts:read",
  ],
  SUPPLY_CHAIN_MANAGER: [
    "suppliers:read",
    "suppliers:write",
    "products:read",
    "products:write",
    "warehouses:read",
    "inventory:read",
    "inventory:write",
    "inventory:transactions:read",
    "orders:read",
    "orders:write",
    "shipments:read",
    "shipments:write",
    "analytics:read",
    "alerts:read",
  ],
  ANALYST: [
    "analytics:read",
    "inventory:read",
    "shipments:read",
    "suppliers:read",
    "alerts:read",
  ],
};

export function hasPermission(role: UserRole, ...permissions: Permission[]): boolean {
  const userPermissions = ROLE_PERMISSIONS[role] || [];
  return permissions.every((p) => userPermissions.includes(p));
}

export function hasRole(userRole: UserRole, ...roles: UserRole[]): boolean {
  return roles.includes(userRole);
}

export function getVisibleNavItems(userRole: UserRole): NavItem[] {
  return NAVIGATION_CONFIG.flatMap((section) =>
    section.items.filter((item) => {
      if (item.adminOnly && userRole !== "ADMIN") return false;
      if (item.requiredRoles && !hasRole(userRole, ...item.requiredRoles)) return false;
      if (item.requiredPermissions && !hasPermission(userRole, ...item.requiredPermissions)) return false;
      return true;
    })
  );
}

export const DASHBOARD_API_CONFIG: Record<UserRole, string[]> = {
  ADMIN: [
    "analyticsApi.getOverview",
    "analyticsApi.getInventory",
    "analyticsApi.getShipments",
    "analyticsApi.getSuppliers",
    "analyticsApi.getBottlenecks",
    "alertsApi.list",
  ],
  // No analytics:read on the backend — operational APIs scoped to the
  // manager's assigned warehouse only.
  WAREHOUSE_MANAGER: [
    "warehousesApi.get",
    "inventoryApi.list",
    "inventoryApi.transactions",
    "shipmentsApi.list",
    "ordersApi.list",
    "alertsApi.list",
  ],
  SUPPLY_CHAIN_MANAGER: [
    "analyticsApi.getOverview",
    "analyticsApi.getInventory",
    "analyticsApi.getShipments",
    "analyticsApi.getSuppliers",
    "analyticsApi.getBottlenecks",
    "alertsApi.list",
  ],
  ANALYST: [
    "analyticsApi.getOverview",
    "analyticsApi.getInventory",
    "analyticsApi.getShipments",
    "analyticsApi.getSuppliers",
    "analyticsApi.getBottlenecks",
    "alertsApi.list",
  ],
};

export const PAGE_PERMISSIONS: Record<string, { permissions?: Permission[]; roles?: UserRole[] }> = {
  "/": {},
  "/inventory": { permissions: ["inventory:read"] },
  "/orders": { permissions: ["orders:read"] },
  "/shipments": { permissions: ["shipments:read"] },
  "/products": { permissions: ["products:read"] },
  "/suppliers": { permissions: ["suppliers:read"] },
  "/warehouses": { permissions: ["warehouses:read"] },
  "/alerts": { permissions: ["alerts:read"] },
  "/analytics": { permissions: ["analytics:read"], roles: ["ADMIN", "SUPPLY_CHAIN_MANAGER", "ANALYST"] },
  "/admin/users": { permissions: ["users:read"], roles: ["ADMIN"] },
};