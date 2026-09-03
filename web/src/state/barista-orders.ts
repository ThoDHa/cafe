import type { Order, ServerEvent } from "../api/client";

export interface BoardState {
  active: Order[];
  done: Order[];
}

export type BoardAction =
  | { type: "snapshot"; orders: Order[] }
  | { type: "event"; event: ServerEvent };

export const DONE_LANE_CAP = 10;

function byNewest(first: Order, second: Order): number {
  return second.createdAt.localeCompare(first.createdAt);
}

export function boardReducer(
  state: BoardState,
  action: BoardAction,
): BoardState {
  switch (action.type) {
    case "snapshot":
      return { active: [...action.orders].sort(byNewest), done: state.done };
    case "event": {
      const { event } = action;
      if (event.type === "order:new") {
        if (state.active.some((order) => order.id === event.order.id)) {
          return state;
        }
        return {
          active: [event.order, ...state.active].sort(byNewest),
          done: state.done,
        };
      }
      if (event.type !== "order:status") {
        return state;
      }
      const { order } = event;
      const known =
        state.active.some((entry) => entry.id === order.id) ||
        state.done.some((entry) => entry.id === order.id);
      if (!known) {
        return state;
      }
      if (order.status === "completed" || order.status === "cancelled") {
        return {
          active: state.active.filter((entry) => entry.id !== order.id),
          done: [order, ...state.done.filter((entry) => entry.id !== order.id)]
            .sort(byNewest)
            .slice(0, DONE_LANE_CAP),
        };
      }
      return {
        active: state.active
          .map((entry) => (entry.id === order.id ? order : entry))
          .sort(byNewest),
        done: state.done,
      };
    }
  }
}

export type BoardActionKind = "start" | "complete" | "cancel";

export interface TransitionRequest {
  orderId: string;
  status: "in_progress" | "completed" | "cancelled";
}

export function buildTransition(
  order: Order,
  action: BoardActionKind,
): TransitionRequest | null {
  switch (action) {
    case "start":
      return order.status === "placed"
        ? { orderId: order.id, status: "in_progress" }
        : null;
    case "complete":
      return order.status === "placed" || order.status === "in_progress"
        ? { orderId: order.id, status: "completed" }
        : null;
    case "cancel":
      return order.status === "placed"
        ? { orderId: order.id, status: "cancelled" }
        : null;
  }
}
