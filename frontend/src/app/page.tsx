"use client";

import React from "react";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import AdminDashboard from "@/components/dashboard/AdminDashboard";
import WarehouseManagerDashboard from "@/components/dashboard/WarehouseManagerDashboard";
import { useAuth } from "@/context/AuthContext";

// Role-specific dashboard entry point. Every authenticated role can view "/"
// (see PAGE_PERMISSIONS), but each role only mounts the dashboard whose API
// calls it is authorized for — so no role fires requests that 403:
//
// - ADMIN / SUPPLY_CHAIN_MANAGER / ANALYST → full analytics dashboard
//   (all hold analytics:read + alerts:read).
// - WAREHOUSE_MANAGER → warehouse-scoped operational dashboard (no
//   analyticsApi calls; the backend denies analytics:read to this role).
export default function DashboardPage() {
  const { user, isLoading } = useAuth();

  return (
    <ProtectedRoute>
      <AppLayout>
        {isLoading || !user ? (
          <div className="flex items-center justify-center py-24">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
          </div>
        ) : user.role === "WAREHOUSE_MANAGER" ? (
          <WarehouseManagerDashboard warehouseId={user.warehouse_id} />
        ) : user.role === "SUPPLY_CHAIN_MANAGER" ? (
          <AdminDashboard
            title="Supply Chain Dashboard"
            subtitle="Network-wide operational KPIs across suppliers, inventory, and shipments"
          />
        ) : user.role === "ANALYST" ? (
          <AdminDashboard
            title="Analytics Dashboard"
            subtitle="Read-only network insights: inventory, shipment, supplier, and bottleneck analytics"
          />
        ) : (
          <AdminDashboard />
        )}
      </AppLayout>
    </ProtectedRoute>
  );
}
