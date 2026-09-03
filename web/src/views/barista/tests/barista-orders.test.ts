import { describe, expect, it } from "vitest";
import type { Order } from "../../../api/client";
import type { OrderLineView } from "../../ordering/lib/lineViews";
import {
  boardReducer,
  buildTransition,
  DONE_LANE_CAP,
  type BoardState,
} from "../../../state/barista-orders";

function line(itemId: string, name: string, quantity = 1): OrderLineView {
  return {
    itemId,
    itemName: name,
    itemNameVi: name,
    temperature: "iced",
    quantity,
    milkOptionId: null,
    milkOptionName: null,
    sweetenerTypeId: null,
    sweetenerTypeName: null,
    sweetnessLevelId: null,
    sweetnessLevelName: null,
    coldFoamId: null,
    coldFoamName: null,
    notes: null,
  };
}

function order(
  id: string,
  number: number,
  status: Order["status"],
  minutesAgo = 0,
): Order {
  const at = new Date(Date.parse("2026-09-03T12:00:00Z") - minutesAgo * 60_000);
  return {
    id,
    orderNumber: number,
    status,
    customerName: null,
    items: [line("sua-da", "Sữa Đá")],
    createdAt: at.toISOString(),
    updatedAt: at.toISOString(),
  };
}

describe("barista board store", () => {
  it("loads a snapshot wholesale, newest first", () => {
    const state = boardReducer(
      { active: [], done: [] },
      {
        type: "snapshot",
        orders: [order("b", 2, "placed", 1), order("a", 1, "in_progress", 5)],
      },
    );

    expect(state.active.map((entry) => entry.id)).toEqual(["b", "a"]);
    expect(state.done).toEqual([]);
  });

  it("snapshot replacement heals drifted state", () => {
    const drifted: BoardState = {
      active: [order("ghost", 9, "placed")],
      done: [],
    };
    const state = boardReducer(drifted, {
      type: "snapshot",
      orders: [order("a", 1, "placed")],
    });

    expect(state.active.map((entry) => entry.id)).toEqual(["a"]);
  });

  it("inserts a new order at the head of the queue", () => {
    let state: BoardState = { active: [order("a", 1, "placed", 3)], done: [] };
    state = boardReducer(state, {
      type: "event",
      event: { type: "order:new", order: order("b", 2, "placed", 0) },
    });

    expect(state.active.map((entry) => entry.id)).toEqual(["b", "a"]);
  });

  it("moves an order to done on completion, keeping newest first", () => {
    let state: BoardState = {
      active: [order("a", 1, "placed", 3), order("b", 2, "in_progress", 1)],
      done: [order("z", 0, "completed", 9)],
    };
    state = boardReducer(state, {
      type: "event",
      event: {
        type: "order:status",
        order: order("a", 1, "completed", 3),
      },
    });

    expect(state.active.map((entry) => entry.id)).toEqual(["b"]);
    expect(state.done.map((entry) => entry.id)).toEqual(["a", "z"]);
  });

  it("keeps cancelled orders in done for the record", () => {
    let state: BoardState = { active: [order("a", 1, "placed")], done: [] };
    state = boardReducer(state, {
      type: "event",
      event: {
        type: "order:status",
        order: order("a", 1, "cancelled"),
      },
    });

    expect(state.active).toEqual([]);
    expect(state.done.map((entry) => entry.status)).toEqual(["cancelled"]);
  });

  it("caps the done lane, dropping the oldest", () => {
    let state: BoardState = { active: [], done: [] };
    for (let index = 1; index <= DONE_LANE_CAP + 2; index += 1) {
      state = boardReducer(state, {
        type: "event",
        event: {
          type: "order:new",
          order: order(`done-${index}`, index, "placed", 60 - index),
        },
      });
      state = boardReducer(state, {
        type: "event",
        event: {
          type: "order:status",
          order: order(`done-${index}`, index, "completed", 60 - index),
        },
      });
    }

    expect(state.done).toHaveLength(DONE_LANE_CAP);
    expect(state.done[0].id).toBe(`done-${DONE_LANE_CAP + 2}`);
    expect(state.active).toEqual([]);
  });

  it("ignores events for orders not on the board", () => {
    const state = boardReducer(
      { active: [order("a", 1, "placed")], done: [] },
      {
        type: "event",
        event: {
          type: "order:status",
          order: order("stranger", 7, "completed"),
        },
      },
    );

    expect(state.active.map((entry) => entry.id)).toEqual(["a"]);
    expect(state.done).toEqual([]);
  });
});

describe("transition builder", () => {
  it("starts a placed order", () => {
    expect(buildTransition(order("a", 1, "placed"), "start")).toEqual({
      orderId: "a",
      status: "in_progress",
    });
  });

  it("completes from placed (fast path) and from in_progress", () => {
    expect(buildTransition(order("a", 1, "placed"), "complete")).toEqual({
      orderId: "a",
      status: "completed",
    });
    expect(
      buildTransition(order("b", 2, "in_progress"), "complete"),
    ).toEqual({ orderId: "b", status: "completed" });
  });

  it("cancels only a placed order", () => {
    expect(buildTransition(order("a", 1, "placed"), "cancel")).toEqual({
      orderId: "a",
      status: "cancelled",
    });
    expect(buildTransition(order("b", 2, "in_progress"), "cancel")).toBeNull();
    expect(buildTransition(order("c", 3, "completed"), "cancel")).toBeNull();
  });

  it("refuses to start an order already making", () => {
    expect(buildTransition(order("b", 2, "in_progress"), "start")).toBeNull();
  });
});
