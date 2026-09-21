"use client";

import React, { useEffect, useState, useCallback } from "react";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import AppLayout from "@/components/common/AppLayout";
import DataTable, { Column } from "@/components/common/DataTable";
import Modal from "@/components/common/Modal";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { useAuth } from "@/context/AuthContext";
import { productsApi, suppliersApi } from "@/lib/api";
import { Product, Supplier, PaginationMeta } from "@/types/api";
import { Package, Plus, Edit2, Filter } from "lucide-react";

export default function ProductsPage() {
  const { hasPermission } = useAuth();
  const canWriteProducts = hasPermission("products:write");

  const [products, setProducts] = useState<Product[]>([]);
  const [meta, setMeta] = useState<PaginationMeta>({ page: 1, limit: 10, total: 0, pages: 1 });
  const [loading, setLoading] = useState(true);

  // Filters
  const [skuSearch, setSkuSearch] = useState("");
  const [supplierFilter, setSupplierFilter] = useState<string>("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  // Create/Edit Modals
  const [modalOpen, setModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [formData, setFormData] = useState({
    sku: "",
    name: "",
    description: "",
    unit: "piece",
    reorder_threshold: "50",
    supplier_id: "",
    is_active: true,
  });
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string; details?: any } | null>(null);

  const loadSuppliers = async () => {
    try {
      const res = await suppliersApi.list({ limit: 100 });
      setSuppliers(res.data || []);
    } catch (err) {
      console.error("Failed to load suppliers:", err);
    }
  };

  const loadProducts = useCallback(async (page = 1, limit = 10) => {
    setLoading(true);
    try {
      const res = await productsApi.list({
        page,
        limit,
        sku: skuSearch || undefined,
        supplier_id: supplierFilter ? Number(supplierFilter) : undefined,
      });
      setProducts(res.data || []);
      setMeta(res.meta);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to load products" });
    } finally {
      setLoading(false);
    }
  }, [skuSearch, supplierFilter]);

  useEffect(() => {
    loadSuppliers();
  }, []);

  useEffect(() => {
    loadProducts(1, meta.limit);
  }, [loadProducts, meta.limit]);

  const handleOpenCreate = () => {
    setEditingProduct(null);
    setFormData({
      sku: "",
      name: "",
      description: "",
      unit: "piece",
      reorder_threshold: "50",
      supplier_id: suppliers[0]?.id ? String(suppliers[0].id) : "",
      is_active: true,
    });
    setModalOpen(true);
  };

  const handleOpenEdit = (product: Product) => {
    setEditingProduct(product);
    setFormData({
      sku: product.sku,
      name: product.name,
      description: product.description || "",
      unit: product.unit,
      reorder_threshold: String(product.reorder_threshold),
      supplier_id: String(product.supplier_id),
      is_active: product.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || (!editingProduct && !formData.sku)) {
      setFeedback({ type: "error", message: "Please fill in all required fields." });
      return;
    }

    setSaving(true);
    setFeedback(null);
    try {
      if (editingProduct) {
        await productsApi.update(editingProduct.id, {
          name: formData.name,
          description: formData.description,
          unit: formData.unit,
          reorder_threshold: Number(formData.reorder_threshold),
          is_active: formData.is_active,
        });
        setFeedback({ type: "success", message: "Product updated successfully." });
      } else {
        await productsApi.create({
          supplier_id: Number(formData.supplier_id),
          sku: formData.sku,
          name: formData.name,
          description: formData.description || undefined,
          unit: formData.unit,
          reorder_threshold: Number(formData.reorder_threshold),
        });
        setFeedback({ type: "success", message: "Product created successfully." });
      }
      setModalOpen(false);
      loadProducts(meta.page, meta.limit);
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.message || "Failed to save product",
        details: err.details,
      });
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<Product>[] = [
    {
      key: "sku",
      header: "SKU",
      render: (p) => <span className="font-mono font-semibold text-slate-900">{p.sku}</span>,
    },
    {
      key: "name",
      header: "Product Name",
      render: (p) => (
        <div>
          <p className="font-medium text-slate-900">{p.name}</p>
          {p.description && <p className="text-xs text-slate-400 truncate max-w-xs">{p.description}</p>}
        </div>
      ),
    },
    {
      key: "supplier",
      header: "Supplier",
      render: (p) => {
        const sup = p.supplier || suppliers.find((s) => s.id === p.supplier_id);
        return <span className="text-xs text-slate-600">{sup?.name || `#${p.supplier_id}`}</span>;
      },
    },
    {
      key: "unit",
      header: "Unit",
      render: (p) => <span className="text-xs text-slate-600 font-mono">{p.unit}</span>,
    },
    {
      key: "threshold",
      header: "Reorder Threshold",
      render: (p) => (
        <span className="font-semibold text-slate-800">
          {Number(p.reorder_threshold).toLocaleString()}
        </span>
      ),
    },
    {
      key: "is_active",
      header: "Status",
      render: (p) => <StatusBadge isActive={p.is_active} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (p) =>
        canWriteProducts ? (
          <button
            onClick={() => handleOpenEdit(p)}
            className="rounded p-1 text-slate-400 hover:text-indigo-600 hover:bg-slate-100"
            title="Edit product"
          >
            <Edit2 className="h-4 w-4" />
          </button>
        ) : null,
    },
  ];

  return (
    <ProtectedRoute requiredPermissions={["products:read"]}>
      <AppLayout>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                Products Catalog
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1">
                Maintain product definitions, units of measure, and automatic reorder thresholds
              </p>
            </div>
            {canWriteProducts && (
              <button
                onClick={handleOpenCreate}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
              >
                <Plus className="h-4 w-4" /> Add Product
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

          {/* Filter Bar */}
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
            <div className="flex items-center gap-1 text-slate-400">
              <Filter className="h-4 w-4" />
              <span className="text-xs font-medium text-slate-700">Filters:</span>
            </div>
            <input
              type="text"
              placeholder="Search SKU..."
              value={skuSearch}
              onChange={(e) => setSkuSearch(e.target.value)}
              className="rounded-md border border-slate-300 py-1.5 px-2.5 text-xs text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <select
              value={supplierFilter}
              onChange={(e) => setSupplierFilter(e.target.value)}
              className="rounded-md border border-slate-300 py-1.5 px-2.5 text-xs bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">All Suppliers</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.code})
                </option>
              ))}
            </select>
            {(skuSearch || supplierFilter) && (
              <button
                onClick={() => {
                  setSkuSearch("");
                  setSupplierFilter("");
                }}
                className="text-xs text-indigo-600 hover:text-indigo-800 ml-auto"
              >
                Reset filters
              </button>
            )}
          </div>

          {/* Table */}
          <DataTable
            columns={columns}
            data={products}
            isLoading={loading}
            meta={meta}
            onPageChange={(p) => loadProducts(p, meta.limit)}
            onLimitChange={(l) => loadProducts(1, l)}
            emptyMessage="No products found."
          />

          {/* Create/Edit Modal */}
          <Modal
            isOpen={modalOpen}
            onClose={() => setModalOpen(false)}
            title={editingProduct ? `Edit Product: ${editingProduct.sku}` : "Add New Product"}
          >
            <form onSubmit={handleSubmit} className="space-y-4">
              {!editingProduct && (
                <div>
                  <label className="block text-xs font-semibold text-slate-700">Supplier *</label>
                  <select
                    required
                    value={formData.supplier_id}
                    onChange={(e) => setFormData({ ...formData, supplier_id: e.target.value })}
                    className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">Select supplier</option>
                    {suppliers.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.code})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700">SKU *</label>
                <input
                  type="text"
                  required
                  disabled={!!editingProduct}
                  value={formData.sku}
                  onChange={(e) => setFormData({ ...formData, sku: e.target.value })}
                  placeholder="e.g. SKU-1001"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs font-mono text-slate-700 disabled:bg-slate-100 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Product Name *</label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. Hexagonal Titanium Bolt"
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Description</label>
                <textarea
                  rows={2}
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Specifications or notes..."
                  className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700">Unit *</label>
                  <input
                    type="text"
                    required
                    value={formData.unit}
                    onChange={(e) => setFormData({ ...formData, unit: e.target.value })}
                    placeholder="e.g. piece, kg, reel"
                    className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700">
                    Reorder Threshold *
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="any"
                    required
                    value={formData.reorder_threshold}
                    onChange={(e) => setFormData({ ...formData, reorder_threshold: e.target.value })}
                    className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              {editingProduct && (
                <div className="flex items-center gap-2 pt-2">
                  <input
                    type="checkbox"
                    id="is_active"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <label htmlFor="is_active" className="text-xs font-medium text-slate-700">
                    Active in catalog
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
                  {saving ? "Saving..." : editingProduct ? "Save Changes" : "Create Product"}
                </button>
              </div>
            </form>
          </Modal>
        </div>
      </AppLayout>
    </ProtectedRoute>
  );
}

