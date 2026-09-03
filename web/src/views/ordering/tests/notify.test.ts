import { describe, expect, it, vi } from "vitest";
import type { Order } from "../../../api/client";
import {
  createReadyNotifier,
  type NotificationWindow,
  type PermissionState,
} from "../lib/notify";

function makeWindow(
  initial: PermissionState,
  onRequest: () => PermissionState = () => "granted",
): NotificationWindow & { show: ReturnType<typeof vi.fn> } {
  let current = initial;
  const show = vi.fn();
  return {
    permission: () => current,
    requestPermission: async () => {
      current = onRequest();
      return current;
    },
    show,
  };
}

function completedOrder(number = 5): Order {
  return {
    id: "order-1",
    orderNumber: number,
    status: "completed",
    customerName: "Lan",
    items: [],
    createdAt: "2026-09-03T12:00:00Z",
    updatedAt: "2026-09-03T12:02:00Z",
  };
}

describe("ready notifier", () => {
  it("shows nothing before the guest opts in, even when granted", async () => {
    const window = makeWindow("granted");
    const notifier = createReadyNotifier(window);

    notifier.onOrderStatus(completedOrder());

    expect(window.show).not.toHaveBeenCalled();
  });

  it("opts in from the gesture when permission becomes granted", async () => {
    const window = makeWindow("default");
    const notifier = createReadyNotifier(window);

    await expect(notifier.optIn()).resolves.toBe(true);
    expect(notifier.permission).toBe("granted");
  });

  it("shows exactly one notification on the completed transition", async () => {
    const window = makeWindow("default");
    const notifier = createReadyNotifier(window);
    await notifier.optIn();

    notifier.onOrderStatus(completedOrder());
    notifier.onOrderStatus(completedOrder());

    expect(window.show).toHaveBeenCalledTimes(1);
    const [title, body] = window.show.mock.calls[0];
    expect(title).toContain("5");
    expect(body).toContain("Lan");
  });

  it("shows nothing on non-completed transitions", async () => {
    const window = makeWindow("granted");
    const notifier = createReadyNotifier(window);
    await notifier.optIn();

    notifier.onOrderStatus({ ...completedOrder(), status: "in_progress" });
    notifier.onOrderStatus({ ...completedOrder(), status: "cancelled" });

    expect(window.show).not.toHaveBeenCalled();
  });

  it("does not notify when permission is denied", async () => {
    const window = makeWindow("default", () => "denied");
    const notifier = createReadyNotifier(window);

    await expect(notifier.optIn()).resolves.toBe(false);
    notifier.onOrderStatus(completedOrder());

    expect(window.show).not.toHaveBeenCalled();
  });

  it("treats unsupported notification as never notifying", () => {
    const window: NotificationWindow = {
      permission: () => "unsupported",
      requestPermission: async () => "unsupported",
      show: vi.fn(),
    };
    const notifier = createReadyNotifier(window);

    void notifier.optIn();
    notifier.onOrderStatus(completedOrder());

    expect(window.show).not.toHaveBeenCalled();
  });
});
