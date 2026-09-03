import { describe, expect, it, vi } from "vitest";
import type { Order } from "../../../api/client";
import {
  createNewOrderAlert,
  type AlertPorts,
} from "../lib/alert";

function makePorts(options: {
  hidden?: boolean;
  permission?: "granted" | "denied" | "default";
  muted?: boolean;
}) {
  const show = vi.fn();
  const chime = vi.fn();
  const ports: AlertPorts = {
    hidden: () => options.hidden ?? false,
    notification: {
      permission: () => options.permission ?? "default",
      requestPermission: async () => options.permission ?? "default",
      show,
    },
    audio: { chime },
    muted: () => options.muted ?? false,
  };
  return Object.assign(ports, { show, chime });
}

function newOrder(): Order {
  return {
    id: "order-1",
    orderNumber: 12,
    status: "placed",
    customerName: "Lan",
    items: [
      {
        itemId: "sua-da",
        itemName: "Vietnamese Iced Coffee",
        itemNameVi: "Sữa Đá",
        temperature: "iced",
        quantity: 2,
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

describe("new order alert", () => {
  it("chimes on every new order when not muted", () => {
    const ports = makePorts({});
    const alert = createNewOrderAlert(ports);

    alert.onNewOrder(newOrder());

    expect(ports.chime).toHaveBeenCalledTimes(1);
  });

  it("stays silent when muted", () => {
    const ports = makePorts({ muted: true });
    const alert = createNewOrderAlert(ports);

    alert.onNewOrder(newOrder());

    expect(ports.chime).not.toHaveBeenCalled();
  });

  it("notifies with number and item count when hidden and granted", () => {
    const ports = makePorts({ hidden: true, permission: "granted" });
    const alert = createNewOrderAlert(ports);

    alert.onNewOrder(newOrder());

    expect(ports.show).toHaveBeenCalledTimes(1);
    const [title, body] = ports.show.mock.calls[0];
    expect(title).toContain("12");
    expect(body).toContain("2");
    expect(body.toLowerCase()).toContain("sữa đá");
  });

  it("does not notify when the board is visible", () => {
    const ports = makePorts({ hidden: false, permission: "granted" });
    const alert = createNewOrderAlert(ports);

    alert.onNewOrder(newOrder());

    expect(ports.show).not.toHaveBeenCalled();
  });

  it("does not notify when permission is denied", () => {
    const ports = makePorts({ hidden: true, permission: "denied" });
    const alert = createNewOrderAlert(ports);

    alert.onNewOrder(newOrder());

    expect(ports.show).not.toHaveBeenCalled();
  });

  it("still chimes when notification is unavailable but audio is on", () => {
    const ports = makePorts({ hidden: true, permission: "denied" });
    const alert = createNewOrderAlert(ports);

    alert.onNewOrder(newOrder());

    expect(ports.chime).toHaveBeenCalledTimes(1);
    expect(ports.show).not.toHaveBeenCalled();
  });
});
