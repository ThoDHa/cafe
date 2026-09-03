import { describe, expect, it } from "vitest";
import type { OrderCreate } from "../../../api/client";
import type { CartLine } from "../../../state/cart";
import { buildOrderCreate } from "../lib/payload";

const firstLine: CartLine = {
  itemId: "matcha-sua",
  temperature: "iced",
  quantity: 2,
  milkOptionId: "oat-milk",
  sweetenerTypeId: "condensed-milk",
  sweetnessLevelId: "50",
  coldFoamId: "foam-salted",
  notes: "extra cold",
};

const secondLine: CartLine = {
  itemId: "kem-sua",
  temperature: "iced",
  quantity: 1,
  milkOptionId: null,
  sweetenerTypeId: null,
  sweetnessLevelId: null,
  coldFoamId: null,
  notes: null,
};

describe("order payload builder", () => {
  it("builds a contract-shaped OrderCreate from cart lines", () => {
    const payload: OrderCreate = buildOrderCreate(
      [firstLine, secondLine],
      "  Lan  ",
    );

    expect(payload).toEqual({
      customerName: "Lan",
      items: [firstLine, secondLine],
    });
  });

  it("normalizes a blank customer name to null", () => {
    expect(buildOrderCreate([firstLine], "   ").customerName).toBeNull();
    expect(buildOrderCreate([firstLine], null).customerName).toBeNull();
  });

  it("keeps every selection field of every line", () => {
    const payload = buildOrderCreate([firstLine], null);

    expect(payload.items[0]).toEqual(firstLine);
  });
});
