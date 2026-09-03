import { describe, expect, it } from "vitest";
import type { components } from "../../../api/client";
import {
  createCartReducer,
  lineKey,
  type CartLine,
} from "../../../state/cart";

type OrderRules = components["schemas"]["OrderRules"];

const rules: OrderRules = {
  notesMaxLength: 200,
  minQuantity: 1,
  maxQuantity: 10,
};

const reducer = createCartReducer(rules);

function line(overrides: Partial<CartLine> = {}): CartLine {
  return {
    itemId: "matcha-sua",
    temperature: "iced",
    quantity: 1,
    milkOptionId: "oat-milk",
    sweetenerTypeId: "condensed-milk",
    sweetnessLevelId: "50",
    coldFoamId: "foam-salted",
    notes: null,
    ...overrides,
  };
}

describe("cart reducer", () => {
  it("stores the full selection snapshot when adding", () => {
    const cart = reducer([], { type: "add", line: line({ quantity: 2 }) });

    expect(cart).toHaveLength(1);
    expect(cart[0]).toEqual(line({ quantity: 2 }));
  });

  it("merges quantity when the identical selection is added again", () => {
    const cart = reducer([], { type: "add", line: line({ quantity: 1 }) });

    const merged = reducer(cart, { type: "add", line: line({ quantity: 2 }) });

    expect(merged).toHaveLength(1);
    expect(merged[0]?.quantity).toBe(3);
  });

  it("keeps distinct lines for distinct customizations of one item", () => {
    const hot = reducer([], {
      type: "add",
      line: line({ temperature: "hot", coldFoamId: null }),
    });
    const withFoam = reducer(hot, { type: "add", line: line() });
    const otherNotes = reducer(withFoam, {
      type: "add",
      line: line({ notes: "extra cold" }),
    });

    expect(otherNotes).toHaveLength(3);
    expect(new Set(otherNotes.map(lineKey)).size).toBe(3);
  });

  it("clamps the merged quantity to the maximum", () => {
    const cart = reducer([], { type: "add", line: line({ quantity: 9 }) });

    const merged = reducer(cart, { type: "add", line: line({ quantity: 5 }) });

    expect(merged).toHaveLength(1);
    expect(merged[0]?.quantity).toBe(10);
  });

  it("clamps direct quantity adjustments into the allowed bounds", () => {
    const cart = reducer([], { type: "add", line: line() });
    const key = lineKey(line());

    const raised = reducer(cart, { type: "setQuantity", key, quantity: 99 });
    expect(raised[0]?.quantity).toBe(10);

    const lowered = reducer(raised, { type: "setQuantity", key, quantity: 0 });
    expect(lowered[0]?.quantity).toBe(1);
  });

  it("ignores quantity adjustments for unknown keys", () => {
    const cart = reducer([], { type: "add", line: line() });

    const unchanged = reducer(cart, {
      type: "setQuantity",
      key: "missing-key",
      quantity: 5,
    });

    expect(unchanged).toBe(cart);
  });

  it("removes only the targeted line", () => {
    const kept = line();
    const dropped = line({ temperature: "hot", coldFoamId: null });
    const base = reducer([], { type: "add", line: kept });
    const cart = reducer(base, { type: "add", line: dropped });

    const withoutDropped = reducer(cart, {
      type: "remove",
      key: lineKey(dropped),
    });

    expect(withoutDropped).toHaveLength(1);
    expect(withoutDropped[0]).toEqual(kept);
  });

  it("clears every line", () => {
    const cart = reducer([], { type: "add", line: line() });

    expect(reducer(cart, { type: "clear" })).toEqual([]);
  });

  it("derives one stable key per selection snapshot", () => {
    expect(lineKey(line({ notes: "a" }))).toBe(lineKey(line({ notes: "a" })));
    expect(lineKey(line({ notes: "a" }))).not.toBe(lineKey(line({ notes: "b" })));
    expect(lineKey(line({ temperature: "hot" }))).not.toBe(lineKey(line()));
  });
});
