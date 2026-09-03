import type { OrderCreate } from "../../../api/client";
import type { CartLine } from "../../../state/cart";

export function buildOrderCreate(
  lines: CartLine[],
  customerName: string | null,
): OrderCreate {
  const trimmedName = customerName?.trim();
  return {
    customerName: trimmedName && trimmedName.length > 0 ? trimmedName : null,
    items: lines.map((line) => ({
      itemId: line.itemId,
      temperature: line.temperature,
      quantity: line.quantity,
      milkOptionId: line.milkOptionId,
      sweetenerTypeId: line.sweetenerTypeId,
      sweetnessLevelId: line.sweetnessLevelId,
      coldFoamId: line.coldFoamId,
      notes: line.notes,
    })),
  };
}
