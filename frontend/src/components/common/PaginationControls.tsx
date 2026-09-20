import React from "react";
import { PaginationMeta } from "@/types/api";

interface PaginationControlsProps {
  meta?: PaginationMeta;
  onPageChange: (newPage: number) => void;
  onLimitChange?: (newLimit: number) => void;
  isLoading?: boolean;
}

export default function PaginationControls({
  meta,
  onPageChange,
  onLimitChange,
  isLoading = false,
}: PaginationControlsProps) {
  if (!meta) return null;

  const { page, pages, total, limit } = meta;

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-slate-200 bg-white px-4 py-3 sm:px-6">
      <div className="flex items-center gap-2 text-sm text-slate-700">
        <span>
          Showing <span className="font-semibold">{total > 0 ? (page - 1) * limit + 1 : 0}</span> to{" "}
          <span className="font-semibold">{Math.min(page * limit, total)}</span> of{" "}
          <span className="font-semibold">{total}</span> results
        </span>
        {onLimitChange && (
          <div className="flex items-center gap-1.5 ml-4">
            <label htmlFor="perPage" className="text-xs text-slate-500">
              Per page:
            </label>
            <select
              id="perPage"
              value={limit}
              onChange={(e) => onLimitChange(Number(e.target.value))}
              disabled={isLoading}
              className="rounded border border-slate-300 py-1 px-2 text-xs bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1 || isLoading}
          className="relative inline-flex items-center rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Previous
        </button>
        <span className="text-xs text-slate-600 px-1">
          Page {page} of {Math.max(pages, 1)}
        </span>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages || isLoading}
          className="relative inline-flex items-center rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </div>
  );
}

