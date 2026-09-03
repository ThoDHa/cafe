import type { components, OrderLine } from "../../../api/client";
import { menuDocument } from "./menuData";

export type OrderLineView = components["schemas"]["OrderLineView"];

function optionName(optionId: string | null): string | null {
  if (optionId === null) {
    return null;
  }
  for (const group of menuDocument.modifierGroups) {
    const option = group.options.find((candidate) => candidate.id === optionId);
    if (option) {
      return option.name;
    }
  }
  throw new Error(`menu lookup: unknown modifier option "${optionId}"`);
}

export function toLineView(line: OrderLine): OrderLineView {
  const item = menuDocument.items.find((candidate) => candidate.id === line.itemId);
  if (!item) {
    throw new Error(`menu lookup: unknown item "${line.itemId}"`);
  }
  return {
    itemId: line.itemId,
    itemName: item.name,
    itemNameVi: item.nameVi,
    temperature: line.temperature,
    quantity: line.quantity,
    milkOptionId: line.milkOptionId,
    milkOptionName: optionName(line.milkOptionId),
    sweetenerTypeId: line.sweetenerTypeId,
    sweetenerTypeName: optionName(line.sweetenerTypeId),
    sweetnessLevelId: line.sweetnessLevelId,
    sweetnessLevelName: optionName(line.sweetnessLevelId),
    coldFoamId: line.coldFoamId,
    coldFoamName: optionName(line.coldFoamId),
    notes: line.notes,
  };
}
