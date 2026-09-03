import type { components, OrderLine } from "../api/client";

export type CartLine = OrderLine;
type OrderRules = components["schemas"]["OrderRules"];

export type CartAction =
  | { type: "add"; line: CartLine }
  | { type: "setQuantity"; key: string; quantity: number }
  | { type: "remove"; key: string }
  | { type: "clear" };

export function lineKey(line: CartLine): string {
  return JSON.stringify([
    line.itemId,
    line.temperature,
    line.milkOptionId,
    line.sweetenerTypeId,
    line.sweetnessLevelId,
    line.coldFoamId,
    line.notes,
  ]);
}

function clampQuantity(quantity: number, rules: OrderRules): number {
  return Math.min(Math.max(quantity, rules.minQuantity), rules.maxQuantity);
}

export function createCartReducer(rules: OrderRules) {
  return function cartReducer(
    cart: CartLine[],
    action: CartAction,
  ): CartLine[] {
    switch (action.type) {
      case "add": {
        const key = lineKey(action.line);
        const existing = cart.find((line) => lineKey(line) === key);
        if (!existing) {
          return [
            ...cart,
            { ...action.line, quantity: clampQuantity(action.line.quantity, rules) },
          ];
        }
        return cart.map((line) =>
          line === existing
            ? {
                ...line,
                quantity: clampQuantity(
                  existing.quantity + action.line.quantity,
                  rules,
                ),
              }
            : line,
        );
      }
      case "setQuantity": {
        if (!cart.some((line) => lineKey(line) === action.key)) {
          return cart;
        }
        return cart.map((line) =>
          lineKey(line) === action.key
            ? { ...line, quantity: clampQuantity(action.quantity, rules) }
            : line,
        );
      }
      case "remove":
        return cart.filter((line) => lineKey(line) !== action.key);
      case "clear":
        return [];
    }
  };
}
