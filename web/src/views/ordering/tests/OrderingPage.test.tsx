import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type {
  ApiClient,
  EventListener,
  MenuDocument,
  Order,
  ServerEvent,
} from "../../../api/client";
import { menuDocument } from "../lib/menuData";
import OrderingPage from "../OrderingPage";

function placedOrder(number = 1): Order {
  return {
    id: "order-1",
    orderNumber: number,
    status: "placed",
    customerName: null,
    items: [
      {
        itemId: "matcha-sua",
        itemName: "Matcha Latte",
        itemNameVi: "Matcha Sữa",
        temperature: "iced",
        quantity: 1,
        milkOptionId: null,
        milkOptionName: null,
        sweetenerTypeId: null,
        sweetenerTypeName: null,
        sweetnessLevelId: null,
        sweetnessLevelName: null,
        coldFoamId: null,
        coldFoamName: null,
        notes: null,
      },
    ],
    createdAt: "2026-09-03T12:00:00Z",
    updatedAt: "2026-09-03T12:00:00Z",
  };
}

function fakeClient(menu: MenuDocument = menuDocument) {
  const listeners = new Set<EventListener>();
  const order = placedOrder();
  const client: ApiClient & {
    emit: (event: ServerEvent) => void;
    placeOrder: ReturnType<typeof vi.fn>;
  } = {
    getMenu: () => Promise.resolve(menu),
    placeOrder: vi.fn(() => Promise.resolve(order)),
    getOrder: vi.fn(() => Promise.resolve(order)),
    listActiveOrders: vi.fn(() => Promise.resolve([order])),
    transitionStatus: vi.fn(() => Promise.resolve(order)),
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

describe("OrderingPage", () => {
  it("renders every section with its items after the menu loads", async () => {
    render(<OrderingPage client={fakeClient()} />);

    expect(await screen.findByRole("heading", { name: "Cà Phê" })).toBeInTheDocument();
    for (const heading of ["Mát-cha", "Trà", "Giải Khát", "Kem"]) {
      expect(
        screen.getByRole("heading", { name: heading }),
      ).toBeInTheDocument();
    }
    expect(screen.getByText("Sữa Đá")).toBeInTheDocument();
    expect(screen.getByText("Kem Muối")).toBeInTheDocument();
  });

  it("shows only offered temperature pills per item", async () => {
    render(<OrderingPage client={fakeClient()} />);
    await screen.findByText("Cortado");

    const cortadoCard = screen.getByRole("button", {
      name: /Cortado/,
    });
    expect(cortadoCard).toHaveTextContent("nóng");
    expect(cortadoCard).not.toHaveTextContent("đá");
  });

  it("offers cold foam only once the drink is iced", async () => {
    const user = userEvent.setup();
    render(<OrderingPage client={fakeClient()} />);
    await screen.findByText("Matcha Sữa");

    await user.click(screen.getByRole("button", { name: /Matcha Sữa/ }));

    const sheet = await screen.findByRole("dialog", { name: "Matcha Sữa" });
    expect(sheet).toHaveTextContent("Sweetener");
    expect(sheet).not.toHaveTextContent("Cold foam");

    await user.click(screen.getByRole("button", { name: "đá" }));

    expect(screen.getByRole("dialog", { name: "Matcha Sữa" })).toHaveTextContent(
      "Cold foam",
    );
  });

  it("walks the full flow: customize, cart, place, confirmation", async () => {
    const user = userEvent.setup();
    const client = fakeClient();
    render(<OrderingPage client={client} />);
    await screen.findByText("Matcha Sữa");

    await user.click(screen.getByRole("button", { name: /Matcha Sữa/ }));
    await user.click(
      await screen.findByRole("button", { name: "Add to cart" }),
    );
    await user.click(await screen.findByRole("button", { name: "Place order" }));

    expect(await screen.findByText("#1")).toBeInTheDocument();
    expect(screen.getByText("Placed")).toBeInTheDocument();
    expect(client.placeOrder).toHaveBeenCalledTimes(1);
  });

  it("reflects live status changes from the event feed", async () => {
    const user = userEvent.setup();
    const client = fakeClient();
    render(<OrderingPage client={client} />);
    await screen.findByText("Matcha Sữa");

    await user.click(screen.getByRole("button", { name: /Matcha Sữa/ }));
    await user.click(
      await screen.findByRole("button", { name: "Add to cart" }),
    );
    await user.click(await screen.findByRole("button", { name: "Place order" }));
    await screen.findByText("Placed");

    client.emit({
      type: "order:status",
      order: { ...placedOrder(), status: "completed" },
    });

    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument());
  });

  it("reorders from device history into the cart", async () => {
    const user = userEvent.setup();
    const client = fakeClient();
    render(<OrderingPage client={client} />);
    await screen.findByText("Matcha Sữa");

    await user.click(screen.getByRole("button", { name: /Matcha Sữa/ }));
    await user.click(
      await screen.findByRole("button", { name: "Add to cart" }),
    );
    await user.click(await screen.findByRole("button", { name: "Place order" }));
    await screen.findByText("#1");

    await user.click(screen.getByRole("button", { name: "Your orders" }));
    await user.click(await screen.findByRole("button", { name: "Reorder" }));

    const cart = await screen.findByRole("dialog", { name: "Cart" });
    expect(cart).toHaveTextContent("Matcha Sữa");
  });
});
