import { PublicTrackingEvent } from "@/types/api";

export const TRACKING_NUMBER_PATTERN = /^TRK-[0-9A-F]{8}$/;

const LIFECYCLE_ORDER = ["PACKED", "IN_TRANSIT", "DELIVERED"];

/** Normalize raw user input the same way the backend does (trim + uppercase). */
export function normalizeTrackingNumber(input: string): string {
  return (input || "").trim().toUpperCase();
}

/** Client-side format pre-check so obviously-invalid input never hits the API. */
export function isValidTrackingNumberFormat(input: string): boolean {
  return TRACKING_NUMBER_PATTERN.test(normalizeTrackingNumber(input));
}

/** Chronologically ascending copy of a tracking timeline (stable on ties). */
export function sortTimelineAsc<T extends PublicTrackingEvent>(events: T[]): T[] {
  return [...events].sort((a, b) => {
    if (a.changed_at < b.changed_at) return -1;
    if (a.changed_at > b.changed_at) return 1;
    return 0;
  });
}

/** Position of a status in the PACKED → IN_TRANSIT → DELIVERED lifecycle. */
export function trackingStepIndex(status: string): number {
  return LIFECYCLE_ORDER.indexOf(status);
}

export function trackingStepLabels(): string[] {
  return [...LIFECYCLE_ORDER];
}
