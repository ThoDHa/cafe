export type { components } from "./schema";

import type { components } from "./schema";

type Schemas = components["schemas"];

export type MenuDocument = Schemas["MenuDocument"];
export type MenuItem = Schemas["MenuItem"];
export type Category = Schemas["Category"];
export type ModifierGroup = Schemas["ModifierGroup"];
export type ModifierOption = Schemas["ModifierOption"];
export type Temperature = Schemas["Temperature"];
export type OrderLine = Schemas["OrderLine"];
export type OrderCreate = Schemas["OrderCreate"];
export type Order = Schemas["Order"];
export type OrderStatus = Schemas["OrderStatus"];
export type ApiError = Schemas["ApiError"];
export type ServerEvent =
  | Schemas["OrderNewEvent"]
  | Schemas["OrderStatusEvent"]
  | Schemas["HeartbeatEvent"];

export type EventListener = (event: ServerEvent) => void;

/**
 * The typed seam both surfaces code against: the guest ordering view
 * and the barista queue view. The real fetch/EventSource client lands
 * at integration; until then the programmable mock in mock.ts is the
 * test double and development stand-in.
 */
export interface ApiClient {
  getMenu(): Promise<MenuDocument>;
  placeOrder(request: OrderCreate): Promise<Order>;
  getOrder(orderId: string): Promise<Order>;
  listActiveOrders(): Promise<Order[]>;
  transitionStatus(orderId: string, status: OrderStatus): Promise<Order>;
  subscribeToEvents(listener: EventListener): () => void;
}
