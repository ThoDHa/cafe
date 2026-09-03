import { afterEach, describe, expect, it, vi } from "vitest";
import { createDevClient } from "../lib/devClient";
import type { OrderLine } from "../../../api/client";

const matchaLine: OrderLine = {
  itemId: "matcha-sua",
  temperature: "iced",
  quantity: 2,
  milkOptionId: "oat-milk",
  sweetenerTypeId: "condensed-milk",
  sweetnessLevelId: "50",
  coldFoamId: "foam-salted",
  notes: null,
};

afterEach(() => {
  vi.useRealTimers();
});

describe("dev client stand-in", () => {
  it("serves the real menu", async () => {
    const client = createDevClient();
    const menu = await client.getMenu();
    expect(menu.items).toHaveLength(36);
    expect(menu.categories).toHaveLength(5);
  });

  it("places orders with sequential daily numbers and resolved names", async () => {
    const client = createDevClient();
    const first = await client.placeOrder({
      customerName: "Lan",
      items: [matchaLine],
    });
    const second = await client.placeOrder({
      customerName: null,
      items: [matchaLine],
    });

    expect(first.orderNumber).toBe(1);
    expect(first.status).toBe("placed");
    expect(first.customerName).toBe("Lan");
    expect(first.items[0]?.itemName).toBe("Matcha Latte");
    expect(second.orderNumber).toBe(2);
  });

  it("emits status transitions to subscribers on a schedule", async () => {
    vi.useFakeTimers();
    const client = createDevClient();
    const seen: string[] = [];
    client.subscribeToEvents((event) => {
      if (event.type === "order:status") {
        seen.push(event.order.status);
      }
    });

    const order = await client.placeOrder({
      customerName: null,
      items: [matchaLine],
    });
    await vi.advanceTimersByTimeAsync(9000);
    expect(seen).toEqual(["in_progress"]);

    await vi.advanceTimersByTimeAsync(30000);
    expect(seen).toEqual(["in_progress", "completed"]);
    expect(order.status).toBe("placed");
  });

  it("returns placed orders by id and rejects unknown ids", async () => {
    const client = createDevClient();
    const order = await client.placeOrder({
      customerName: null,
      items: [matchaLine],
    });

    expect((await client.getOrder(order.id)).orderNumber).toBe(order.orderNumber);
    await expect(client.getOrder("missing-id")).rejects.toMatchObject({
      payload: { error: "order not found" },
    });
  });

  it("applies legal transitions and rejects illegal ones", async () => {
    const client = createDevClient();
    const order = await client.placeOrder({
      customerName: null,
      items: [matchaLine],
    });

    const making = await client.transitionStatus(order.id, "in_progress");
    expect(making.status).toBe("in_progress");

    await expect(
      client.transitionStatus(order.id, "placed"),
    ).rejects.toMatchObject({
      payload: { error: "illegal transition" },
    });
  });
});
