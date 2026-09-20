import React, { ReactNode } from "react";
import PaginationControls from "./PaginationControls";
import { PaginationMeta } from "@/types/api";

export interface Column<T> {
  key: string;
  header: string;
  className?: string;
  render?: (item: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  isLoading?: boolean;
  emptyMessage?: string;
  meta?: PaginationMeta;
  onPageChange?: (page: number) => void;
  onLimitChange?: (limit: number) => void;
  onRowClick?: (item: T) => void;
}

export default function DataTable<T extends { id?: number | string }>({
  columns,
  data,
  isLoading = false,
  emptyMessage = "No records found.",
  meta,
  onPageChange,
  onLimitChange,
  onRowClick,
}: DataTableProps<T>) {
  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm text-slate-600">
          <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <tr>
              {columns.map((col) => (
                <th key={col.key} scope="col" className={`px-4 py-3 sm:px-6 ${col.className || ""}`}>
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {isLoading ? (
              Array.from({ length: 5 }).map((_, index) => (
                <tr key={`skeleton-${index}`} className="animate-pulse">
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-4 sm:px-6">
                      <div className="h-4 w-3/4 rounded bg-slate-200" />
                    </td>
                  ))}
                </tr>
              ))
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12 text-center text-slate-500 sm:px-6">
                  <p className="text-sm font-medium">{emptyMessage}</p>
                </td>
              </tr>
            ) : (
              data.map((item, index) => (
                <tr
                  key={item.id ? String(item.id) : `row-${index}`}
                  onClick={() => onRowClick && onRowClick(item)}
                  className={`hover:bg-slate-50 transition-colors ${
                    onRowClick ? "cursor-pointer" : ""
                  }`}
                >
                  {columns.map((col) => (
                    <td key={col.key} className={`px-4 py-3.5 sm:px-6 ${col.className || ""}`}>
                      {col.render ? col.render(item) : (item as any)[col.key] ?? "-"}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {meta && onPageChange && (
        <PaginationControls
          meta={meta}
          onPageChange={onPageChange}
          onLimitChange={onLimitChange}
          isLoading={isLoading}
        />
      )}
    </div>
  );
}

