import React from "react";
import { AlertCircle, CheckCircle, Info, X } from "lucide-react";

interface FeedbackAlertProps {
  type: "success" | "error" | "info" | "warning";
  message: string;
  details?: any;
  onDismiss?: () => void;
}

export default function FeedbackAlert({
  type,
  message,
  details,
  onDismiss,
}: FeedbackAlertProps) {
  if (!message) return null;

  const bgStyles = {
    success: "bg-emerald-50 border-emerald-200 text-emerald-800",
    error: "bg-red-50 border-red-200 text-red-800",
    warning: "bg-amber-50 border-amber-200 text-amber-800",
    info: "bg-blue-50 border-blue-200 text-blue-800",
  }[type];

  const IconComponent = {
    success: CheckCircle,
    error: AlertCircle,
    warning: AlertCircle,
    info: Info,
  }[type];

  let detailsText: string | null = null;
  if (details) {
    if (typeof details === "string") {
      detailsText = details;
    } else if (Array.isArray(details)) {
      detailsText = details
        .map((d) => (typeof d === "object" ? `${d.loc?.join(".") || "field"}: ${d.msg}` : String(d)))
        .join("; ");
    } else if (typeof details === "object") {
      detailsText = JSON.stringify(details);
    }
  }

  return (
    <div className={`mb-4 flex items-start justify-between rounded-lg border p-4 ${bgStyles}`}>
      <div className="flex items-start gap-3">
        <IconComponent className="h-5 w-5 flex-shrink-0 mt-0.5" />
        <div className="text-sm">
          <p className="font-medium">{message}</p>
          {detailsText && <p className="mt-1 text-xs opacity-90 font-mono">{detailsText}</p>}
        </div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="ml-4 inline-flex flex-shrink-0 rounded p-1 hover:bg-black/5 focus:outline-none"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

