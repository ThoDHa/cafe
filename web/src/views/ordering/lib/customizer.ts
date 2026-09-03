import type {
  components,
  MenuDocument,
  MenuItem,
  ModifierGroup,
  ModifierOption,
  Temperature,
} from "../../../api/client";
import type { CartLine } from "../../../state/cart";

export type ModifierDimension = components["schemas"]["ModifierDimension"];

export interface Selection {
  itemId: string;
  temperature: Temperature;
  milkOptionId: string | null;
  sweetenerTypeId: string | null;
  sweetnessLevelId: string | null;
  coldFoamId: string | null;
  notes: string;
}

export interface GroupView {
  group: ModifierGroup;
  options: ModifierOption[];
  defaultOptionId: string | null;
}

type DimensionField = keyof Pick<
  Selection,
  | "milkOptionId"
  | "sweetenerTypeId"
  | "sweetnessLevelId"
  | "coldFoamId"
>;

const DIMENSION_FIELDS: Record<ModifierDimension, DimensionField> = {
  milk: "milkOptionId",
  sweetener_type: "sweetenerTypeId",
  sweetness_level: "sweetnessLevelId",
  cold_foam: "coldFoamId",
};

const FOAM_OFFERED_AT: Temperature = "iced";

export function groupsForItem(menu: MenuDocument, itemId: string): ModifierGroup[] {
  const ids = new Set(menu.items.find((item) => item.id === itemId)?.modifierGroupIds);
  return menu.modifierGroups.filter((group) => ids.has(group.id));
}

export function offeredTemperatures(item: MenuItem): Temperature[] {
  return item.temperatures;
}

export function resolveDefault(
  group: ModifierGroup,
  temperature: Temperature,
): string | null {
  if (group.defaultOptionId) {
    return group.defaultOptionId;
  }
  return group.defaultByTemperature?.[temperature] ?? null;
}

export function visibleGroups(
  menu: MenuDocument,
  item: MenuItem,
  temperature: Temperature,
): GroupView[] {
  return groupsForItem(menu, item.id)
    .filter(
      (group) =>
        group.dimension !== "cold_foam" || temperature === FOAM_OFFERED_AT,
    )
    .map((group) => ({
      group,
      options: group.options.filter((option) =>
        option.temperatures.includes(temperature),
      ),
      defaultOptionId: resolveDefault(group, temperature),
    }))
    .filter((view) => view.options.length > 0);
}

export function initialSelection(menu: MenuDocument, item: MenuItem): Selection {
  const temperature = item.temperatures[0];
  if (!temperature) {
    throw new Error(`menu integrity: item "${item.id}" offers no temperature`);
  }
  const selection: Selection = {
    itemId: item.id,
    temperature,
    milkOptionId: null,
    sweetenerTypeId: null,
    sweetnessLevelId: null,
    coldFoamId: null,
    notes: "",
  };
  for (const view of visibleGroups(menu, item, temperature)) {
    const field = DIMENSION_FIELDS[view.group.dimension];
    selection[field] = view.defaultOptionId;
  }
  return selection;
}

export function changeTemperature(
  menu: MenuDocument,
  item: MenuItem,
  selection: Selection,
  temperature: Temperature,
): Selection {
  if (selection.temperature === temperature) {
    return selection;
  }
  const views = visibleGroups(menu, item, temperature);
  const next: Selection = { ...selection, temperature };
  for (const group of groupsForItem(menu, item.id)) {
    const field = DIMENSION_FIELDS[group.dimension];
    const view = views.find((candidate) => candidate.group.id === group.id);
    if (!view) {
      next[field] = null;
      continue;
    }
    if (!view.options.some((option) => option.id === next[field])) {
      next[field] = view.defaultOptionId;
    }
  }
  return next;
}

export function selectOption(
  selection: Selection,
  dimension: ModifierDimension,
  optionId: string | null,
): Selection {
  return { ...selection, [DIMENSION_FIELDS[dimension]]: optionId };
}

export function selectionToLine(selection: Selection, quantity: number): CartLine {
  const notes = selection.notes.trim();
  return {
    itemId: selection.itemId,
    temperature: selection.temperature,
    quantity,
    milkOptionId: selection.milkOptionId,
    sweetenerTypeId: selection.sweetenerTypeId,
    sweetnessLevelId: selection.sweetnessLevelId,
    coldFoamId: selection.coldFoamId,
    notes: notes.length > 0 ? notes : null,
  };
}
