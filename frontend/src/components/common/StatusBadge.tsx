import React from "react";
import { OrderStatus, ShipmentStatus, AlertSeverity, AlertType } from "@/types/api";

interface StatusBadgeProps {
  status?: OrderStatus | ShipmentStatus | string;
  severity?: AlertSeverity;
  alertType?: AlertType;
  isActive?: boolean;
  isDelayed?: boolean;
  size?: "sm" | "md";
}

export default function StatusBadge({
  status,
  severity,
  alertType,
  isActive,
  isDelayed,
  size = "md",
}: StatusBadgeProps) {
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs font-medium";

  if (isDelayed) {
    return (
      <span
        className={`inline-flex items-center rounded-full bg-red-100 text-red-800 font-semibold border border-red-200 ${sizeClasses}`}
      >
        DELAYED
      </span>
    );
  }

  if (isActive !== undefined) {
    return isActive ? (
      <span className={`inline-flex items-center rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 ${sizeClasses}`}>
        Active
      </span>
    ) : (
      <span className={`inline-flex items-center rounded-full bg-slate-100 text-slate-600 border border-slate-200 ${sizeClasses}`}>
        Inactive
      </span>
    );
  }

  if (severity) {
    switch (severity) {
      case "CRITICAL":
        return <span className={`inline-flex items-center rounded-full bg-red-100 text-red-800 border border-red-200 ${sizeClasses}`}>CRITICAL</span>;
      case "WARNING":
        return <span className={`inline-flex items-center rounded-full bg-amber-100 text-amber-800 border border-amber-200 ${sizeClasses}`}>WARNING</span>;
      case "INFO":
      default:
        return <span className={`inline-flex items-center rounded-full bg-blue-100 text-blue-800 border border-blue-200 ${sizeClasses}`}>INFO</span>;
    }
  }

  if (alertType) {
    switch (alertType) {
      case "LOW_STOCK":
        return <span className={`inline-flex items-center rounded-full bg-amber-50 text-amber-700 border border-amber-300 ${sizeClasses}`}>LOW STOCK</span>;
      case "SHIPMENT_OVERDUE":
        return <span className={`inline-flex items-center rounded-full bg-red-50 text-red-700 border border-red-300 ${sizeClasses}`}>OVERDUE</span>;
    }
  }

  if (status) {
    switch (status) {
      // Order statuses
      case "PLACED":
        return <span className={`inline-flex items-center rounded-full bg-sky-50 text-sky-700 border border-sky-200 ${sizeClasses}`}>PLACED</span>;
      case "CONFIRMED":
        return <span className={`inline-flex items-center rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 ${sizeClasses}`}>CONFIRMED</span>;
      case "FULFILLED":
        return <span className={`inline-flex items-center rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 ${sizeClasses}`}>FULFILLED</span>;
      case "CANCELLED":
        return <span className={`inline-flex items-center rounded-full bg-slate-100 text-slate-600 border border-slate-200 ${sizeClasses}`}>CANCELLED</span>;

      // Shipment statuses
      case "PACKED":
        return <span className={`inline-flex items-center rounded-full bg-amber-50 text-amber-700 border border-amber-200 ${sizeClasses}`}>PACKED</span>;
      case "IN_TRANSIT":
        return <span className={`inline-flex items-center rounded-full bg-blue-50 text-blue-700 border border-blue-200 ${sizeClasses}`}>IN TRANSIT</span>;
      case "DELIVERED":
        return <span className={`inline-flex items-center rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 ${sizeClasses}`}>DELIVERED</span>;

      default:
        return <span className={`inline-flex items-center rounded-full bg-slate-100 text-slate-700 border border-slate-200 ${sizeClasses}`}>{status}</span>;
    }
  }

  return null;
}

