"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  PackageSearch,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Truck,
  Package,
  Clock,
  AlertTriangle,
  SearchX,
} from "lucide-react";
import StatusBadge from "@/components/common/StatusBadge";
import FeedbackAlert from "@/components/common/FeedbackAlert";
import { trackingApi } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { PublicTrackingInfo } from "@/types/api";
import { normalizeTrackingNumber, sortTimelineAsc, trackingStepIndex } from "@/lib/tracking";

const STEP_ICONS = [Package, Truck, CheckCircle2];
const STEP_LABELS = ["Packed", "In transit", "Delivered"];

// Public page: no ProtectedRoute, no AppLayout, no login required.
export default function TrackingResultPage() {
  const params = useParams<{ trackingNumber: string }>();
  const router = useRouter();
  const rawNumber = params?.trackingNumber ? decodeURIComponent(params.trackingNumber) : "";
  const trackingNumber = normalizeTrackingNumber(rawNumber);

  const [info, setInfo] = useState<PublicTrackingInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lookupInput, setLookupInput] = useState("");

  useEffect(() => {
    if (!trackingNumber) {
      setLoading(false);
      setNotFound(true);
      return;
    }
    let cancelled = false;
    const fetchTracking = async () => {
      setLoading(true);
      setNotFound(false);
      setError(null);
      try {
        const data = await trackingApi.get(trackingNumber);
        if (!cancelled) setInfo(data);
      } catch (err: any) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(err?.message || "Failed to load tracking information.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchTracking();
    return () => {
      cancelled = true;
    };
  }, [trackingNumber]);

  const handleLookup = (e: React.FormEvent) => {
    e.preventDefault();
    const normalized = normalizeTrackingNumber(lookupInput);
    if (!normalized) return;
    router.push(`/tracking/${encodeURIComponent(normalized)}`);
  };

  const timeline = info ? sortTimelineAsc(info.timeline) : [];
  const currentStep = info ? trackingStepIndex(String(info.status)) : -1;

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
          className="ml-auto text-xs font-medium text-indigo-600 hover:text-indigo-700"
        >
          Staff login
        </Link>
      </header>

      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
        <Link
          href="/track"
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800 mb-6"
        >
          <ArrowLeft className="h-4 w-4" /> Track another package
        </Link>

        {loading ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-slate-200 bg-white py-24">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
            <p className="text-sm text-slate-500">Looking up {trackingNumber || "shipment"}…</p>
          </div>
        ) : notFound ? (
          <div className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
              <SearchX className="h-6 w-6" />
            </div>
            <h1 className="mt-4 text-lg font-bold text-slate-900">Tracking number not found</h1>
            <p className="mt-1 text-xs text-slate-500">
              No shipment matches{" "}
              <span className="font-mono font-semibold text-slate-700">{trackingNumber || rawNumber}</span>.
              Please check the number and try again.
            </p>
            <form onSubmit={handleLookup} className="mx-auto mt-6 flex max-w-sm gap-2">
              <input
                type="text"
                value={lookupInput}
                onChange={(e) => setLookupInput(e.target.value)}
                placeholder="TRK-________"
                autoComplete="off"
                spellCheck={false}
                className="block w-full rounded-md border border-slate-300 p-2 font-mono text-sm uppercase text-slate-900 focus:border-indigo-500 focus:outline-none"
              />
              <button
                type="submit"
                className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700"
              >
                Retry <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </form>
          </div>
        ) : error ? (
          <FeedbackAlert type="error" message={error} onDismiss={() => setError(null)} />
        ) : info ? (
          <div className="space-y-6">
            {/* Current status card */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Tracking number
                  </p>
                  <p className="mt-0.5 font-mono text-lg font-bold text-slate-900">
                    {info.tracking_number}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <StatusBadge status={String(info.status)} />
                  {info.is_delayed && <StatusBadge isDelayed={true} />}
                </div>
              </div>

              {info.is_delayed && (
                <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">
                  <AlertTriangle className="h-4 w-4 flex-shrink-0 text-red-600 mt-0.5" />
                  <p>
                    <span className="font-semibold">This shipment is delayed.</span> It is past
                    its expected delivery date and has not been delivered yet.
                  </p>
                </div>
              )}

              <dl className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="rounded-lg bg-slate-50 border border-slate-100 p-3">
                  <dt className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
                    <Clock className="h-3.5 w-3.5" /> Expected delivery
                  </dt>
                  <dd className="mt-1 text-sm font-semibold text-slate-900">
                    {info.expected_delivery_at
                      ? new Date(info.expected_delivery_at).toLocaleString()
                      : "Not set"}
                  </dd>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-100 p-3">
                  <dt className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Actual delivery
                  </dt>
                  <dd className="mt-1 text-sm font-semibold text-slate-900">
                    {info.actual_delivery_at
                      ? new Date(info.actual_delivery_at).toLocaleString()
                      : "Not delivered yet"}
                  </dd>
                </div>
              </dl>
            </div>

            {/* Progress steps */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">Delivery progress</h2>
              <div className="mt-4 flex items-center">
                {STEP_LABELS.map((label, idx) => {
                  const Icon = STEP_ICONS[idx];
                  const reached = currentStep >= 0 && idx <= currentStep;
                  const isCurrent = idx === currentStep;
                  return (
                    <React.Fragment key={label}>
                      <div className="flex flex-col items-center gap-1.5">
                        <div
                          className={`flex h-10 w-10 items-center justify-center rounded-full border-2 ${
                            reached
                              ? "border-indigo-600 bg-indigo-600 text-white"
                              : "border-slate-200 bg-slate-50 text-slate-400"
                          }`}
                        >
                          <Icon className="h-5 w-5" />
                        </div>
                        <span
                          className={`text-[11px] font-medium ${
                            isCurrent ? "text-indigo-700 font-semibold" : reached ? "text-slate-700" : "text-slate-400"
                          }`}
                        >
                          {label}
                        </span>
                      </div>
                      {idx < STEP_LABELS.length - 1 && (
                        <div
                          className={`mx-2 mb-6 h-0.5 flex-1 rounded ${
                            currentStep > idx ? "bg-indigo-600" : "bg-slate-200"
                          }`}
                        />
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>

            {/* Timeline */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">Shipment timeline</h2>
              {timeline.length === 0 ? (
                <p className="mt-3 text-xs text-slate-500">No timeline events yet.</p>
              ) : (
                <ol className="mt-4 space-y-0">
                  {timeline.map((event, idx) => (
                    <li key={`${event.status}-${event.changed_at}-${idx}`} className="relative flex gap-3 pb-5 last:pb-0">
                      {idx < timeline.length - 1 && (
                        <span className="absolute left-[7px] top-5 h-full w-px bg-slate-200" aria-hidden />
                      )}
                      <span
                        className={`mt-1 h-2 w-2 flex-shrink-0 rounded-full ${
                          idx === timeline.length - 1 ? "bg-indigo-600" : "bg-slate-300"
                        }`}
                      />
                      <div>
                        <p className="text-xs font-semibold text-slate-900">
                          {String(event.status).replace(/_/g, " ")}
                        </p>
                        <p className="text-[11px] text-slate-500">
                          {new Date(event.changed_at).toLocaleString()}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            {/* New lookup */}
            <form onSubmit={handleLookup} className="flex gap-2">
              <div className="relative flex-1">
                <PackageSearch className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={lookupInput}
                  onChange={(e) => setLookupInput(e.target.value)}
                  placeholder="Track another package (TRK-________)"
                  autoComplete="off"
                  spellCheck={false}
                  className="block w-full rounded-md border border-slate-300 py-2 pl-9 pr-3 font-mono text-sm uppercase text-slate-900 focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <button
                type="submit"
                className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700"
              >
                Track <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </form>
          </div>
        ) : null}
      </main>
    </div>
  );
}
