import type { Order, OrderStatus, ServerEvent } from "../api/client";

export type GuestOrderState = Order | null;

export type GuestOrderEvent =
  | { type: "tracked"; order: Order }
  | { type: "feed"; event: ServerEvent }
  | { type: "refetched"; order: Order }
  | { type: "cleared" };

const STATUS_COPY: Record<OrderStatus, string> = {
  placed: "Placed",
  in_progress: "Making",
  completed: "Ready",
  cancelled: "Cancelled",
};

export function guestStatusCopy(status: OrderStatus): string {
  return STATUS_COPY[status];
}

export function guestOrderReducer(
  state: GuestOrderState,
  event: GuestOrderEvent,
): GuestOrderState {
  switch (event.type) {
    case "tracked":
      return event.order;
    case "feed":
      if (
        event.event.type === "order:status" &&
        state?.id === event.event.order.id
      ) {
        return event.event.order;
      }
      return state;
    case "refetched":
      if (state?.id === event.order.id) {
        return event.order;
      }
      return state;
    case "cleared":
      return null;
  }
}
