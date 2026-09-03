import { describe, expect, it } from "vitest";
import type { Order } from "../../../api/client";
import { guestOrderReducer, guestStatusCopy } from "../../../state/ordering-status";
import { orderFixture, statusEvent } from "../lib/scenarios";
import type { OrderLine } from "../../../api/client";

const matchaLine: OrderLine = {
  itemId: "matcha-sua",
  temperature: "iced",
  quantity: 1,
  milkOptionId: "oat-milk",
  sweetenerTypeId: "condensed-milk",
  sweetnessLevelId: "50",
  coldFoamId: null,
  notes: null,
};

function order(overrides: Partial<Order> = {}): Order {
  return orderFixture({ orderNumber: 7, lines: [matchaLine], ...overrides });
}

describe("guest order status store", () => {
  it("tracks the freshly placed order", () => {
    const placed = order();

    expect(guestOrderReducer(null, { type: "tracked", order: placed })).toEqual(placed);
  });

  it("replaces the snapshot when a feed event carries the tracked order", () => {
    const placed = order();
    const making = statusEvent(placed, "in_progress");

    const next = guestOrderReducer(placed, { type: "feed", event: making });

    expect(next?.status).toBe("in_progress");
    expect(next?.orderNumber).toBe(7);
  });

  it("ignores feed events for other orders and non-order events", () => {
    const placed = order();
    const otherOrder = statusEvent(order({ id: "another-order" }), "completed");
    const heartbeat = {
      type: "heartbeat" as const,
      sentAt: "2026-09-03T15:04:30Z",
    };

    expect(guestOrderReducer(placed, { type: "feed", event: otherOrder })).toBe(placed);
    expect(guestOrderReducer(placed, { type: "feed", event: heartbeat })).toBe(placed);
  });

  it("heals to the refetched snapshot regardless of stale local state", () => {
    const placed = order();
    const staleMaking = statusEvent(placed, "in_progress");
    const seenMaking = guestOrderReducer(placed, { type: "feed", event: staleMaking });
    const healed = order({ status: "completed" });

    const next = guestOrderReducer(seenMaking, { type: "refetched", order: healed });

    expect(next?.status).toBe("completed");
  });

  it("ignores a refetch for a different order id", () => {
    const placed = order();

    const next = guestOrderReducer(placed, {
      type: "refetched",
      order: order({ id: "another-order", status: "completed" }),
    });

    expect(next).toBe(placed);
  });

  it("clears the tracked order", () => {
    const placed = order();

    expect(guestOrderReducer(placed, { type: "cleared" })).toBeNull();
  });
});

describe("guest status copy", () => {
  it("speaks the guest-facing words for every status", () => {
    expect(guestStatusCopy("placed")).toBe("Placed");
    expect(guestStatusCopy("in_progress")).toBe("Making");
    expect(guestStatusCopy("completed")).toBe("Ready");
    expect(guestStatusCopy("cancelled")).toBe("Cancelled");
  });
});
