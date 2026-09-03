import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type {
  ApiClient,
  EventListener,
  Order,
  ServerEvent,
} from "../../../api/client";
import BaristaPage from "../BaristaPage";

function order(
  id: string,
  number: number,
  status: Order["status"],
  minutesAgo = 0,
): Order {
  const at = new Date(Date.now() - minutesAgo * 60_000);
  return {
    id,
    orderNumber: number,
    status,
    customerName: number === 1 ? "Lan" : null,
    items: [
      {
        itemId: "matcha-sua",
        itemName: "Matcha Latte",
        itemNameVi: "Matcha Sữa",
        temperature: "iced",
        quantity: 2,
        milkOptionId: "oat-milk",
        milkOptionName: "Oat milk",
        sweetenerTypeId: null,
        sweetenerTypeName: null,
        sweetnessLevelId: "50",
        sweetnessLevelName: "50%",
        coldFoamId: "foam-salted",
        coldFoamName: "Salted Cold Foam",
        notes: "less ice",
      },
    ],
    createdAt: at.toISOString(),
    updatedAt: at.toISOString(),
  };
}

function fakeClient(snapshot: Order[]) {
  const listeners = new Set<EventListener>();
  const client: ApiClient & {
    emit: (event: ServerEvent) => void;
    transitionStatus: ReturnType<typeof vi.fn>;
  } = {
    getMenu: vi.fn(),
    placeOrder: vi.fn(),
    getOrder: vi.fn((id: string) =>
      Promise.resolve(snapshot.find((entry) => entry.id === id) ?? snapshot[0]),
    ),
    listActiveOrders: vi.fn(() => Promise.resolve(snapshot)),
    transitionStatus: vi.fn(
      (id: string, status: Order["status"]): Promise<Order> =>
        Promise.resolve({ ...snapshot[0], id, status }),
    ),
    subscribeToEvents: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    emit: (event) => {
      for (const listener of listeners) {
        listener(event);
      }
    },
  };
  return client;
}

describe("BaristaPage", () => {
  it("renders the snapshot into lanes with spelled-out detail", async () => {
    render(
      <BaristaPage
        client={fakeClient([
          order("a", 1, "placed", 2),
          order("b", 2, "in_progress", 4),
        ])}
      />,
    );

    const newLane = document.querySelector('[data-lane="new"]') as HTMLElement;
    const makingLane = document.querySelector(
      '[data-lane="making"]',
    ) as HTMLElement;

    expect(await screen.findByText("#1")).toBeInTheDocument();
    expect(newLane).toHaveTextContent("Lan");
    expect(newLane).toHaveTextContent("Matcha Sữa");
    expect(newLane).toHaveTextContent("Oat milk");
    expect(newLane).toHaveTextContent("Salted Cold Foam");
    expect(newLane).toHaveTextContent("less ice");
    expect(makingLane).toHaveTextContent("#2");
  });

  it("starts a placed order through the client", async () => {
    const user = userEvent.setup();
    const client = fakeClient([order("a", 1, "placed")]);
    render(<BaristaPage client={client} />);

    await user.click(await screen.findByRole("button", { name: "Start" }));

    await waitFor(() =>
      expect(client.transitionStatus).toHaveBeenCalledWith(
        "a",
        "in_progress",
      ),
    );
  });

  it("offers cancel only on placed orders", async () => {
    render(
      <BaristaPage
        client={fakeClient([
          order("a", 1, "placed"),
          order("b", 2, "in_progress"),
        ])}
      />,
    );
    await screen.findByText("#1");

    const newLane = document.querySelector('[data-lane="new"]') as HTMLElement;
    const makingLane = document.querySelector(
      '[data-lane="making"]',
    ) as HTMLElement;

    expect(newLane).toHaveTextContent("Cancel");
    expect(makingLane).not.toHaveTextContent("Cancel");
  });

  it("moves a card to done when completion arrives on the feed", async () => {
    const client = fakeClient([order("a", 1, "placed")]);
    render(<BaristaPage client={client} />);
    await screen.findByText("#1");

    client.emit({
      type: "order:status",
      order: order("a", 1, "completed"),
    });

    const doneLane = await waitFor(() => {
      const lane = document.querySelector(
        '[data-lane="done"]',
      ) as HTMLElement;
      expect(lane).toHaveTextContent("#1");
      return lane;
    });
    expect(doneLane).toBeInTheDocument();
  });

  it("flashes a new order arriving on the feed", async () => {
    const client = fakeClient([]);
    render(<BaristaPage client={client} />);

    await waitFor(() =>
      expect(client.listActiveOrders).toHaveBeenCalled(),
    );
    await new Promise((resolve) => setTimeout(resolve, 0));

    client.emit({ type: "order:new", order: order("fresh", 9, "placed") });

    const card = await waitFor(() => {
      const element = screen.getByText("#9").closest("article");
      expect(element).toHaveClass("flash");
      return element as HTMLElement;
    });
    expect(card).toBeInTheDocument();
  });

  it("renders elapsed time since placement", async () => {
    render(<BaristaPage client={fakeClient([order("a", 1, "placed", 2)])} />);

    expect(await screen.findByText(/2:0\d/)).toBeInTheDocument();
  });
});
