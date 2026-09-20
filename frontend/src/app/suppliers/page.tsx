"use client";

import React, { useEffect, useState, useCallback } from "react";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import DataTable, { Column } from "@/components/common/DataTable";
import Modal from "@/components/common/Modal";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { useAuth } from "@/context/AuthContext";
import { suppliersApi } from "@/lib/api";
import { Supplier, PaginationMeta } from "@/types/api";
import { Building2, Plus, Edit2, Search } from "lucide-react";

export default function SuppliersPage() {
  const { hasPermission } = useAuth();
  const canWriteSuppliers = hasPermission("suppliers:write");

  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [meta, setMeta] = useState<PaginationMeta>({ page: 1, limit: 10, total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState("");

  // Create / Edit Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSupplier, setEditingSupplier] = useState<Supplier | null>(null);
  const [formData, setFormData] = useState({
    code: "",
    name: "",
    contact_name: "",
    email: "",
    phone: "",
    address: "",
    is_active: true,
  });
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string; details?: any } | null>(null);

  const loadSuppliers = useCallback(async (page = 1, limit = 10) => {
    setLoading(true);
    try {
      const res = await suppliersApi.list({
        page,
        limit,
        name: search || undefined,
      });
      setSuppliers(res.data || []);
      setMeta(res.meta);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load suppliers" });
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    loadSuppliers(1, meta.limit);
  }, [loadSuppliers, meta.limit]);

  const handleOpenCreate = () => {
    setEditingSupplier(null);
    setFormData({
      code: "",
      name: "",
      contact_name: "",
      email: "",
      phone: "",
      address: "",
      is_active: true,
    });
    setModalOpen(true);
  };

  const handleOpenEdit = (sup: Supplier) => {
    setEditingSupplier(sup);
    setFormData({
      code: sup.code,
      name: sup.name,
      contact_name: sup.contact_name || "",
      email: sup.email || "",
      phone: sup.phone || "",
      address: sup.address || "",
      is_active: sup.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || (!editingSupplier && !formData.code)) {
      setFeedback({ type: "error", message: "Please fill in all required fields." });
      return;
    }

    setSaving(true);
    setFeedback(null);
    try {
      if (editingSupplier) {
        await suppliersApi.update(editingSupplier.id, {
          name: formData.name,
          contact_name: formData.contact_name || undefined,
          email: formData.email || undefined,
          phone: formData.phone || undefined,
          address: formData.address || undefined,
          is_active: formData.is_active,
        });
        setFeedback({ type: "success", message: "Supplier updated successfully." });
      } else {
        await suppliersApi.create({
          code: formData.code,
          name: formData.name,
          contact_name: formData.contact_name || undefined,
          email: formData.email || undefined,
          phone: formData.phone || undefined,
          address: formData.address || undefined,
        });
        setFeedback({ type: "success", message: "Supplier created successfully." });
      }
      setModalOpen(false);
      loadSuppliers(meta.page, meta.limit);
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to save supplier",
        details: err.details,
      });
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<Supplier>[] = [
    {
      key: "code",
      header: "Code",
      render: (s) => <span className="font-mono font-semibold text-slate-900">{s.code}</span>,
    },
    {
      key: "name",
      header: "Supplier Name",
      render: (s) => (
        <div>
          <p className="font-medium text-slate-900">{s.name}</p>
          {s.address && <p className="text-xs text-slate-400">{s.address}</p>}
        </div>
      ),
    },
    {
      key: "contact_name",
      header: "Contact Person",
      render: (s) => <span className="text-slate-700">{s.contact_name || "-"}</span>,
    },
    {
      key: "email",
      header: "Email",
      render: (s) => (
        <span className="text-xs font-mono text-slate-600">{s.email || "-"}</span>
      ),
    },
    {
      key: "phone",
      header: "Phone",
      render: (s) => <span className="text-xs text-slate-600">{s.phone || "-"}</span>,
    },
    {
      key: "is_active",
      header: "Status",
      render: (s) => <StatusBadge isActive={s.is_active} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (s) =>
        canWriteSuppliers ? (
          <button
            onClick={() => handleOpenEdit(s)}
            className="rounded p-1 text-slate-400 hover:text-indigo-600 hover:bg-slate-100"
            title="Edit supplier"
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
                Suppliers Directory
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1">
                Manage supplier partner details, contacts, and vendor codes
              </p>
            </div>
            {canWriteSuppliers && (
              <button
                onClick={handleOpenCreate}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
              >
                <Plus className="h-4 w-4" /> Add Supplier
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

          {/* Search bar */}
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white p-3 shadow-sm max-w-md">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by supplier name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full text-xs text-slate-700 placeholder-slate-400 focus:outline-none"
            />
            {search && (
              <button onClick={() => setSearch("")} className="text-xs text-slate-400 hover:text-slate-600">
                Clear
              </button>
            )}
          </div>

          {/* Table */}
          <DataTable
            columns={columns}
            data={suppliers}
            isLoading={loading}
            meta={meta}
            onPageChange={(p) => loadSuppliers(p, meta.limit)}
            onLimitChange={(l) => loadSuppliers(1, l)}
            emptyMessage="No suppliers found."
          />

          {/* Modal */}
          <Modal
            isOpen={modalOpen}
            onClose={() => setModalOpen(false)}
            title={editingSupplier ? `Edit Supplier: ${editingSupplier.code}` : "Add New Supplier"}
          >
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700">Supplier Code *</label>
                <input
                  type="text"
                  required
                  disabled={!!editingSupplier}
                  value={formData.code}
                  onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                  placeholder="e.g. SUP-001"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs font-mono text-slate-700 disabled:bg-slate-100 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Company Name *</label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. Acme Components LLC"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700">Contact Name</label>
                  <input
                    type="text"
                    value={formData.contact_name}
                    onChange={(e) => setFormData({ ...formData, contact_name: e.target.value })}
                    placeholder="e.g. Jane Doe"
                    className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700">Phone</label>
                  <input
                    type="text"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    placeholder="e.g. +1-555-0100"
                    className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Email Address</label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="e.g. orders@acme.example"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Physical Address</label>
                <input
                  type="text"
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  placeholder="e.g. 100 Industrial Pkwy, City, State"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              {editingSupplier && (
                <div className="flex items-center gap-2 pt-2">
                  <input
                    type="checkbox"
                    id="is_active"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <label htmlFor="is_active" className="text-xs font-medium text-slate-700">
                    Active supplier partner
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
                  {saving ? "Saving..." : editingSupplier ? "Save Changes" : "Create Supplier"}
                </button>
              </div>
            </form>
          </Modal>
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}

