import type { MockStep } from "../../../api/mock";
import type { Order, OrderLine, ServerEvent } from "../../../api/client";
import { menuDocument } from "./menuData";
import { toLineView } from "./lineViews";

const FIXTURE_ORDER_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6";
const FIXTURE_PLACED_AT = "2026-09-03T15:04:05Z";

export interface OrderFixtureInput {
  orderNumber: number;
  lines: OrderLine[];
  status?: Order["status"];
  customerName?: string | null;
  id?: string;
  createdAt?: string;
  updatedAt?: string;
}

export function menuScript(...extra: MockStep[]): MockStep[] {
  return [{ kind: "menu", menu: menuDocument }, ...extra];
}

export function orderFixture(input: OrderFixtureInput): Order {
  return {
    id: input.id ?? FIXTURE_ORDER_ID,
    orderNumber: input.orderNumber,
    status: input.status ?? "placed",
    customerName: input.customerName ?? null,
    items: input.lines.map(toLineView),
    createdAt: input.createdAt ?? FIXTURE_PLACED_AT,
    updatedAt: input.updatedAt ?? FIXTURE_PLACED_AT,
  };
}

export type StatusFeedEvent = Extract<ServerEvent, { type: "order:status" }>;

export function statusEvent(order: Order, status: Order["status"]): StatusFeedEvent {
  return { type: "order:status", order: { ...order, status } };
}

export function healingScript(order: Order): MockStep[] {
  return [{ kind: "order", order }];
}
