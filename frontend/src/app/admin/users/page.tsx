"use client";

import React, { useEffect, useState, useCallback } from "react";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import DataTable, { Column } from "@/components/common/DataTable";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { usersApi } from "@/lib/api";
import { User, PaginationMeta } from "@/types/api";
import { Users } from "lucide-react";

// ADMIN-only (see PAGE_PERMISSIONS). Only ADMIN holds users:read/users:write
// on the backend, so this page is unreachable for all other roles.
export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [meta, setMeta] = useState<PaginationMeta>({ page: 1, limit: 10, total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const loadUsers = useCallback(async (page = 1, limit = 10) => {
    setLoading(true);
    try {
      const res = await usersApi.list({ page, limit });
      setUsers(res.data || []);
      setMeta(res.meta);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load users" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers(1, meta.limit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadUsers]);

  const roleColors: Record<string, string> = {
    ADMIN: "bg-purple-100 text-purple-800 border-purple-200",
    SUPPLY_CHAIN_MANAGER: "bg-blue-100 text-blue-800 border-blue-200",
    WAREHOUSE_MANAGER: "bg-amber-100 text-amber-800 border-amber-200",
    ANALYST: "bg-slate-100 text-slate-800 border-slate-200",
  };

  const columns: Column<User>[] = [
    {
      key: "name",
      header: "Name",
      render: (u) => (
        <div>
          <p className="font-semibold text-slate-900">{u.name}</p>
          <span className="text-xs text-slate-500">{u.email}</span>
        </div>
      ),
    },
    {
      key: "role",
      header: "Role",
      render: (u) => (
        <span
          className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wider ${
            roleColors[u.role] || "bg-slate-100 text-slate-700"
          }`}
        >
          {u.role.replace(/_/g, " ")}
        </span>
      ),
    },
    {
      key: "warehouse",
      header: "Warehouse",
      render: (u) => (
        <span className="text-xs text-slate-600">
          {u.warehouse_id !== null && u.warehouse_id !== undefined ? `#${u.warehouse_id}` : "-"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (u) =>
        u.is_active ? (
          <span className="inline-block rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 border border-emerald-200">
            Active
          </span>
        ) : (
          <span className="inline-block rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500 border border-slate-200">
            Inactive
          </span>
        ),
    },
    {
      key: "created_at",
      header: "Created",
      render: (u) => (
        <span className="text-xs text-slate-500">{new Date(u.created_at).toLocaleString()}</span>
      ),
    },
  ];

  return (
    <ProtectedRoute requiredPermissions={["users:read"]} requiredRoles={["ADMIN"]}>
      <AppLayout>
        <div className="space-y-6">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Users className="h-5 w-5 text-indigo-600" />
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">User Management</h1>
            </div>
            <p className="text-xs sm:text-sm text-slate-500 mt-1">
              All system users and their assigned roles. User creation and role assignment are
              performed by administrators via the backend.
            </p>
          </div>

          {feedback && (
            <FeedbackAlert type={feedback.type} message={feedback.message} onDismiss={() => setFeedback(null)} />
          )}

          <DataTable
            columns={columns}
            data={users}
            isLoading={loading}
            meta={meta}
            onPageChange={(p) => loadUsers(p, meta.limit)}
            onLimitChange={(l) => loadUsers(1, l)}
            emptyMessage="No users found."
          />
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}
