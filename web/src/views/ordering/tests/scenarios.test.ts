import { describe, expect, it } from "vitest";
import { createMockClient } from "../../../api/mock";
import { menuDocument } from "../lib/menuData";
import {
  healingScript,
  menuScript,
  orderFixture,
  statusEvent,
} from "../lib/scenarios";
import type { OrderLine } from "../../../api/client";

const matchaLine: OrderLine = {
  itemId: "matcha-sua",
  temperature: "iced",
  quantity: 2,
  milkOptionId: "oat-milk",
  sweetenerTypeId: "condensed-milk",
  sweetnessLevelId: "50",
  coldFoamId: "foam-salted",
  notes: "extra cold",
};

describe("ordering mock scenarios", () => {
  it("serves the real menu through the mock with all 36 items in 5 sections", async () => {
    const client = createMockClient(menuScript());
    const menu = await client.getMenu();

    expect(menu.categories.map((category) => category.nameVi)).toEqual([
      "Cà Phê",
      "Mát-cha",
      "Trà",
      "Giải Khát",
      "Kem",
    ]);
    expect(menu.items).toHaveLength(36);
    expect(menu.orderRules).toEqual({
      notesMaxLength: 200,
      minQuantity: 1,
      maxQuantity: 10,
    });
    expect(menu).toEqual(menuDocument);
  });

  it("builds a placed order fixture with names resolved from the menu", () => {
    const order = orderFixture({
      orderNumber: 7,
      customerName: "Lan",
      lines: [matchaLine],
    });

    expect(order.status).toBe("placed");
    expect(order.orderNumber).toBe(7);
    expect(order.customerName).toBe("Lan");
    expect(order.items[0]).toMatchObject({
      itemName: "Matcha Latte",
      itemNameVi: "Matcha Sữa",
      milkOptionName: "Oat milk",
      sweetenerTypeName: "Condensed milk",
      sweetnessLevelName: "50%",
      coldFoamName: "Salted Cold Foam",
      notes: "extra cold",
    });
  });

  it("builds a status transition event on the same order id", () => {
    const order = orderFixture({ orderNumber: 7, lines: [matchaLine] });
    const event = statusEvent(order, "in_progress");

    expect(event.type).toBe("order:status");
    expect(event.order.id).toBe(order.id);
    expect(event.order.status).toBe("in_progress");
  });

  it("serves the healed order through the mock for reconnect refetch", async () => {
    const healed = orderFixture({
      orderNumber: 7,
      status: "completed",
      lines: [matchaLine],
    });
    const client = createMockClient(healingScript(healed));

    const refetched = await client.getOrder(healed.id);
    expect(refetched.status).toBe("completed");
  });
});
