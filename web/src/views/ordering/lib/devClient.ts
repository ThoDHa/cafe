import type {
  ApiClient,
  ApiError,
  EventListener,
  Order,
  OrderCreate,
  OrderStatus,
  ServerEvent,
} from "../../../api/client";
import { menuDocument } from "./menuData";
import { toLineView } from "./lineViews";

const ACTIVE_STATUSES: OrderStatus[] = ["placed", "in_progress"];
const MAKING_AFTER_MS = 8000;
const READY_AFTER_MS = 25000;
const LEGAL_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  placed: ["in_progress", "completed", "cancelled"],
  in_progress: ["completed"],
  completed: [],
  cancelled: [],
};

class DevClientError extends Error {
  readonly payload: ApiError;

  constructor(payload: ApiError) {
    super(payload.error);
    this.name = "DevClientError";
    this.payload = payload;
  }
}

function freshId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `dev-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}

/**
 * Development stand-in behind the ApiClient interface for `npm run dev`
 * before integration lands the real fetch/EventSource client: serves the
 * copied real menu, numbers orders sequentially, and walks each placed
 * order to making and then ready on a timer so the live status view has a
 * feed to heal and notify from.
 */
export function createDevClient(): ApiClient {
  const orders = new Map<string, Order>();
  const listeners = new Set<EventListener>();
  let nextOrderNumber = 1;

  const emit = (event: ServerEvent): void => {
    for (const listener of listeners) {
      listener(event);
    }
  };

  const announceLater = (
    orderId: string,
    from: OrderStatus,
    to: OrderStatus,
    delayMs: number,
  ): void => {
    setTimeout(() => {
      const current = orders.get(orderId);
      if (!current || current.status !== from) {
        return;
      }
      const updated: Order = {
        ...current,
        status: to,
        updatedAt: new Date().toISOString(),
      };
      orders.set(updated.id, updated);
      emit({ type: "order:status", order: updated });
    }, delayMs);
  };

  return {
    getMenu() {
      return Promise.resolve(menuDocument);
    },
    placeOrder(request: OrderCreate) {
      const id = freshId();
      const now = new Date().toISOString();
      const order: Order = {
        id,
        orderNumber: nextOrderNumber,
        status: "placed",
        customerName: request.customerName,
        items: request.items.map(toLineView),
        createdAt: now,
        updatedAt: now,
      };
      nextOrderNumber += 1;
      orders.set(id, order);
      announceLater(id, "placed", "in_progress", MAKING_AFTER_MS);
      announceLater(id, "in_progress", "completed", READY_AFTER_MS);
      return Promise.resolve(order);
    },
    getOrder(orderId: string) {
      const order = orders.get(orderId);
      if (!order) {
        return Promise.reject(
          new DevClientError({ error: "order not found", details: [] }),
        );
      }
      return Promise.resolve(order);
    },
    listActiveOrders() {
      const active = [...orders.values()]
        .filter((order) => ACTIVE_STATUSES.includes(order.status))
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
      return Promise.resolve(active);
    },
    transitionStatus(orderId: string, status: OrderStatus) {
      const order = orders.get(orderId);
      if (!order) {
        return Promise.reject(
          new DevClientError({ error: "order not found", details: [] }),
        );
      }
      if (!LEGAL_TRANSITIONS[order.status].includes(status)) {
        return Promise.reject(
          new DevClientError({
            error: "illegal transition",
            details: [`cannot move order from ${order.status} to ${status}`],
          }),
        );
      }
      const updated: Order = {
        ...order,
        status,
        updatedAt: new Date().toISOString(),
      };
      orders.set(orderId, updated);
      emit({ type: "order:status", order: updated });
      return Promise.resolve(updated);
    },
    subscribeToEvents(listener: EventListener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
