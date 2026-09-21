"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PackageSearch, ArrowRight, ShieldCheck } from "lucide-react";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { normalizeTrackingNumber, isValidTrackingNumberFormat } from "@/lib/tracking";

// Public page: no ProtectedRoute, no AppLayout, no login required.
export default function TrackPage() {
  const router = useRouter();
  const [trackingNumber, setTrackingNumber] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const normalized = normalizeTrackingNumber(trackingNumber);
    if (!normalized) {
      setError("Please enter a tracking number.");
      return;
    }
    if (!isValidTrackingNumberFormat(normalized)) {
      setError("Tracking numbers look like TRK-1A2B3C4D. Please check and try again.");
      return;
    }
    setError(null);
    router.push(`/tracking/${encodeURIComponent(normalized)}`);
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <header className="flex h-16 items-center border-b border-slate-200 bg-white px-6">
        <Link href="/track" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold">
            SC
          </div>
          <span className="font-semibold text-slate-800 text-base tracking-tight">
            Supply Chain — Package Tracking
          </span>
        </Link>
        <Link
          href="/login"
          className="ml-auto inline-flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-700"
        >
          <ShieldCheck className="h-4 w-4" /> Staff login
        </Link>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <PackageSearch className="h-6 w-6" />
          </div>
          <h1 className="mt-4 text-center text-xl font-bold tracking-tight text-slate-900">
            Track your package
          </h1>
          <p className="mt-1 text-center text-xs text-slate-500">
            Enter the tracking number shared with you (e.g. TRK-1A2B3C4D).
          </p>

          {error && (
            <div className="mt-4">
              <FeedbackAlert type="error" message={error} onDismiss={() => setError(null)} />
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="tracking-number" className="block text-xs font-semibold text-slate-700">
                Tracking number
              </label>
              <input
                id="tracking-number"
                type="text"
                value={trackingNumber}
                onChange={(e) => setTrackingNumber(e.target.value)}
                placeholder="TRK-________"
                autoComplete="off"
                spellCheck={false}
                className="mt-1 block w-full rounded-md border border-slate-300 p-2.5 font-mono text-sm uppercase text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <button
              type="submit"
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
            >
              Track package <ArrowRight className="h-4 w-4" />
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
