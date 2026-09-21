import { describe, it, expect } from "vitest";
import {
  normalizeTrackingNumber,
  isValidTrackingNumberFormat,
  sortTimelineAsc,
  trackingStepIndex,
  trackingStepLabels,
} from "@/lib/tracking";

describe("normalizeTrackingNumber", () => {
  it("trims whitespace and uppercases input", () => {
    expect(normalizeTrackingNumber("  trk-1a2b3c4d ")).toBe("TRK-1A2B3C4D");
  });

  it("handles empty input", () => {
    expect(normalizeTrackingNumber("")).toBe("");
  });
});

describe("isValidTrackingNumberFormat", () => {
  it("accepts well-formed tracking numbers", () => {
    expect(isValidTrackingNumberFormat("TRK-1A2B3C4D")).toBe(true);
    expect(isValidTrackingNumberFormat("trk-ffffffff")).toBe(true);
  });

  it("rejects malformed input without calling the API", () => {
    expect(isValidTrackingNumberFormat("")).toBe(false);
    expect(isValidTrackingNumberFormat("SHP-00000001")).toBe(false);
    expect(isValidTrackingNumberFormat("TRK-123")).toBe(false);
    expect(isValidTrackingNumberFormat("TRK-1A2B3C4D5E")).toBe(false);
    expect(isValidTrackingNumberFormat("TRK-1a2b3c4g")).toBe(false);
    expect(isValidTrackingNumberFormat("  ")).toBe(false);
  });
});

describe("sortTimelineAsc", () => {
  it("orders timeline events chronologically ascending", () => {
    const events = [
      { status: "DELIVERED", changed_at: "2026-09-03T10:00:00" },
      { status: "PACKED", changed_at: "2026-09-01T10:00:00" },
      { status: "IN_TRANSIT", changed_at: "2026-09-02T10:00:00" },
    ];
    const sorted = sortTimelineAsc(events);
    expect(sorted.map((e) => e.status)).toEqual(["PACKED", "IN_TRANSIT", "DELIVERED"]);
  });

  it("does not mutate the input array", () => {
    const events = [
      { status: "IN_TRANSIT", changed_at: "2026-09-02T10:00:00" },
      { status: "PACKED", changed_at: "2026-09-01T10:00:00" },
    ];
    sortTimelineAsc(events);
    expect(events[0].status).toBe("IN_TRANSIT");
  });
});

describe("trackingStepIndex", () => {
  it("maps the PACKED → IN_TRANSIT → DELIVERED lifecycle in order", () => {
    expect(trackingStepIndex("PACKED")).toBe(0);
    expect(trackingStepIndex("IN_TRANSIT")).toBe(1);
    expect(trackingStepIndex("DELIVERED")).toBe(2);
    expect(trackingStepLabels()).toEqual(["PACKED", "IN_TRANSIT", "DELIVERED"]);
  });

  it("returns -1 for unknown statuses", () => {
    expect(trackingStepIndex("DELAYED")).toBe(-1);
    expect(trackingStepIndex("")).toBe(-1);
  });
});
