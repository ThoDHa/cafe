import type { components, MenuDocument, Order, OrderLine } from "../api/client";

type OrderLineView = components["schemas"]["OrderLineView"];

export interface HistoryEntry {
  id: string;
  orderNumber: number;
  placedAt: string;
  items: OrderLineView[];
}

export interface HistoryStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export const HISTORY_CAP = 50;
const STORAGE_KEY = "cafe:order-history";

export function loadHistory(storage: HistoryStorage): HistoryEntry[] {
  const raw = storage.getItem(STORAGE_KEY);
  if (raw === null) {
    return [];
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(isEntry);
  } catch {
    return [];
  }
}

export function recordOrder(
  storage: HistoryStorage,
  order: Order,
): HistoryEntry[] {
  const entry: HistoryEntry = {
    id: order.id,
    orderNumber: order.orderNumber,
    placedAt: order.createdAt,
    items: order.items,
  };
  const deduped = [
    entry,
    ...loadHistory(storage).filter((existing) => existing.id !== entry.id),
  ];
  const capped = deduped.slice(0, HISTORY_CAP);
  storage.setItem(STORAGE_KEY, JSON.stringify(capped));
  return capped;
}

export function reorderLines(
  menu: MenuDocument,
  entry: HistoryEntry,
): OrderLine[] {
  const liveIds = new Set(menu.items.map((item) => item.id));
  return entry.items
    .filter((view) => liveIds.has(view.itemId))
    .map((view) => ({
      itemId: view.itemId,
      temperature: view.temperature,
      quantity: view.quantity,
      milkOptionId: view.milkOptionId,
      sweetenerTypeId: view.sweetenerTypeId,
      sweetnessLevelId: view.sweetnessLevelId,
      coldFoamId: view.coldFoamId,
      notes: view.notes,
    }));
}

function isEntry(value: unknown): value is HistoryEntry {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<HistoryEntry>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.orderNumber === "number" &&
    typeof candidate.placedAt === "string" &&
    Array.isArray(candidate.items)
  );
}
