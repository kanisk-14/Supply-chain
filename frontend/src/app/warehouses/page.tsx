"use client";

import React, { useEffect, useState, useCallback } from "react";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import DataTable, { Column } from "@/components/common/DataTable";
import Modal from "@/components/common/Modal";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { useAuth } from "@/context/AuthContext";
import { warehousesApi } from "@/lib/api";
import { Warehouse, PaginationMeta } from "@/types/api";
import { Warehouse as WarehouseIcon, Plus, Edit2 } from "lucide-react";

export default function WarehousesPage() {
  const { hasPermission } = useAuth();
  const canWriteWarehouses = hasPermission("warehouses:write");

  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [meta, setMeta] = useState<PaginationMeta>({ page: 1, limit: 10, total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);

  // Modals
  const [modalOpen, setModalOpen] = useState(false);
  const [editingWarehouse, setEditingWarehouse] = useState<Warehouse | null>(null);
  const [formData, setFormData] = useState({
    code: "",
    name: "",
    address: "",
    is_active: true,
  });
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string; details?: any } | null>(null);

  const loadWarehouses = useCallback(async (page = 1, limit = 10) => {
    setLoading(true);
    try {
      const res = await warehousesApi.list({ page, limit });
      setWarehouses(res.data || []);
      setMeta(res.meta);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load warehouses" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWarehouses(1, meta.limit);
  }, [loadWarehouses, meta.limit]);

  const handleOpenCreate = () => {
    setEditingWarehouse(null);
    setFormData({ code: "", name: "", address: "", is_active: true });
    setModalOpen(true);
  };

  const handleOpenEdit = (wh: Warehouse) => {
    setEditingWarehouse(wh);
    setFormData({
      code: wh.code,
      name: wh.name,
      address: wh.address || "",
      is_active: wh.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || (!editingWarehouse && !formData.code)) {
      setFeedback({ type: "error", message: "Please fill in all required fields." });
      return;
    }

    setSaving(true);
    setFeedback(null);
    try {
      if (editingWarehouse) {
        await warehousesApi.update(editingWarehouse.id, {
          name: formData.name,
          address: formData.address || undefined,
          is_active: formData.is_active,
        });
        setFeedback({ type: "success", message: "Warehouse updated successfully." });
      } else {
        await warehousesApi.create({
          code: formData.code,
          name: formData.name,
          address: formData.address || undefined,
        });
        setFeedback({ type: "success", message: "Warehouse created successfully." });
      }
      setModalOpen(false);
      loadWarehouses(meta.page, meta.limit);
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to save warehouse",
        details: err.details,
      });
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<Warehouse>[] = [
    {
      key: "code",
      header: "Warehouse Code",
      render: (w) => <span className="font-mono font-semibold text-slate-900">{w.code}</span>,
    },
    {
      key: "name",
      header: "Warehouse Name",
      render: (w) => <span className="font-medium text-slate-900">{w.name}</span>,
    },
    {
      key: "address",
      header: "Physical Address",
      render: (w) => <span className="text-xs text-slate-600">{w.address || "-"}</span>,
    },
    {
      key: "is_active",
      header: "Status",
      render: (w) => <StatusBadge isActive={w.is_active} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (w) =>
        canWriteWarehouses ? (
          <button
            onClick={() => handleOpenEdit(w)}
            className="rounded p-1 text-slate-400 hover:text-indigo-600 hover:bg-slate-100"
            title="Edit warehouse"
          >
            <Edit2 className="h-4 w-4" />
          </button>
        ) : null,
    },
  ];

  return (
    <ProtectedRoute>
      <AppLayout>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                Warehouses & Hubs
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1">
                Manage storage facilities, logistics hubs, and physical distribution centers
              </p>
            </div>
            {canWriteWarehouses && (
              <button
                onClick={handleOpenCreate}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
              >
                <Plus className="h-4 w-4" /> Add Warehouse
              </button>
            )}
          </div>

          {feedback && (
            <FeedbackAlert
              type={feedback.type}
              message={feedback.message}
              details={feedback.details}
              onDismiss={() => setFeedback(null)}
            />
          )}

          {/* Table */}
          <DataTable
            columns={columns}
            data={warehouses}
            isLoading={loading}
            meta={meta}
            onPageChange={(p) => loadWarehouses(p, meta.limit)}
            onLimitChange={(l) => loadWarehouses(1, l)}
            emptyMessage="No warehouses configured."
          />

          {/* Modal */}
          <Modal
            isOpen={modalOpen}
            onClose={() => setModalOpen(false)}
            title={editingWarehouse ? `Edit Warehouse: ${editingWarehouse.code}` : "Add New Warehouse"}
          >
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700">Warehouse Code *</label>
                <input
                  type="text"
                  required
                  disabled={!!editingWarehouse}
                  value={formData.code}
                  onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                  placeholder="e.g. WH-001"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs font-mono text-slate-700 disabled:bg-slate-100 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Facility Name *</label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. Central Distribution Hub"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Address</label>
                <input
                  type="text"
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  placeholder="e.g. 1 Hub Road, Chicago, IL"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              {editingWarehouse && (
                <div className="flex items-center gap-2 pt-2">
                  <input
                    type="checkbox"
                    id="wh_is_active"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <label htmlFor="wh_is_active" className="text-xs font-medium text-slate-700">
                    Active facility
                  </label>
                </div>
              )}

              <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {saving ? "Saving..." : editingWarehouse ? "Save Changes" : "Create Warehouse"}
                </button>
              </div>
            </form>
          </Modal>
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}

