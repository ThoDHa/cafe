import { describe, expect, it } from "vitest";
import type { Order } from "../../../api/client";
import type { OrderLineView } from "../lib/lineViews";
import { menuDocument } from "../lib/menuData";
import {
  HISTORY_CAP,
  loadHistory,
  recordOrder,
  reorderLines,
  type HistoryStorage,
} from "../../../state/order-history";

function makeStorage(): HistoryStorage & { dump(): string | null } {
  let value: string | null = null;
  return {
    getItem: () => value,
    setItem: (_key: string, next: string) => {
      value = next;
    },
    dump: () => value,
  };
}

function line(itemId: string): OrderLineView {
  const item = menuDocument.items.find((entry) => entry.id === itemId);
  if (!item) {
    throw new Error(`fixture item ${itemId} missing from menu`);
  }
  return {
    itemId,
    itemName: item.name,
    itemNameVi: item.nameVi,
    temperature: item.temperatures[0],
    quantity: 1,
    milkOptionId: null,
    milkOptionName: null,
    sweetenerTypeId: null,
    sweetenerTypeName: null,
    sweetnessLevelId: null,
    sweetnessLevelName: null,
    coldFoamId: null,
    coldFoamName: null,
    notes: null,
  };
}

function makeOrder(number: number, itemIds: string[]): Order {
  return {
    id: `order-${number}`,
    orderNumber: number,
    status: "placed",
    customerName: null,
    items: itemIds.map((itemId) => line(itemId)),
    createdAt: new Date(Date.UTC(2026, 8, 3, 12, number)).toISOString(),
    updatedAt: new Date(Date.UTC(2026, 8, 3, 12, number)).toISOString(),
  };
}

describe("order history", () => {
  it("loads empty from fresh storage", () => {
    expect(loadHistory(makeStorage())).toEqual([]);
  });

  it("loads empty instead of crashing on corrupted JSON", () => {
    const storage = makeStorage();
    storage.setItem("cafe:order-history", "{not json");
    expect(loadHistory(storage)).toEqual([]);
  });

  it("records orders newest first and round-trips through storage", () => {
    const storage = makeStorage();
    recordOrder(storage, makeOrder(1, ["sua-da"]));
    recordOrder(storage, makeOrder(2, ["matcha-sua"]));

    const entries = loadHistory(storage);
    expect(entries.map((entry) => entry.orderNumber)).toEqual([2, 1]);
    expect(entries[0].items[0].itemNameVi).toBe("Matcha Sữa");
  });

  it(`caps history at ${HISTORY_CAP} entries, dropping the oldest`, () => {
    const storage = makeStorage();
    for (let number = 1; number <= HISTORY_CAP + 5; number += 1) {
      recordOrder(storage, makeOrder(number, ["sua-da"]));
    }

    const entries = loadHistory(storage);
    expect(entries).toHaveLength(HISTORY_CAP);
    expect(entries[0].orderNumber).toBe(HISTORY_CAP + 5);
    expect(entries.at(-1)?.orderNumber).toBe(6);
  });

  it("reorders into cart lines, skipping items retired from the menu", () => {
    const storage = makeStorage();
    const order = makeOrder(7, ["sua-da", "ca-phe-kem", "matcha-sua"]);
    const retired = order.items[1];
    const trimmedMenu = {
      ...menuDocument,
      items: menuDocument.items.filter((item) => item.id !== retired.itemId),
    };

    recordOrder(storage, order);
    const [entry] = loadHistory(storage);
    const lines = reorderLines(trimmedMenu, entry);

    expect(lines.map((line) => line.itemId)).toEqual([
      "sua-da",
      "matcha-sua",
    ]);
    expect(lines[0]).toMatchObject({
      itemId: "sua-da",
      temperature: order.items[0].temperature,
      quantity: 1,
      milkOptionId: null,
    });
  });

  it("preserves selections and quantity when reordering", () => {
    const storage = makeStorage();
    const order = makeOrder(3, ["matcha-sua"]);
    order.items[0] = {
      ...order.items[0],
      temperature: "iced",
      quantity: 2,
      milkOptionId: "oat-milk",
      sweetnessLevelId: "50",
    };
    recordOrder(storage, order);

    const [entry] = loadHistory(storage);
    const [line] = reorderLines(menuDocument, entry);
    expect(line).toEqual({
      itemId: "matcha-sua",
      temperature: "iced",
      quantity: 2,
      milkOptionId: "oat-milk",
      sweetenerTypeId: null,
      sweetnessLevelId: "50",
      coldFoamId: null,
      notes: null,
    });
  });
});
